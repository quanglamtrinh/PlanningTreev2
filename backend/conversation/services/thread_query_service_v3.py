from __future__ import annotations

import copy
import logging
import threading
from typing import Any

from backend.config.app_config import (
    get_conversation_v3_bridge_mode,
    get_thread_actor_mode,
    is_conversation_v3_bridge_allowed_for_project,
)
from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.conversation.domain.types_v3 import (
    MINI_JOURNAL_BOUNDARY_TYPES_V3,
    ThreadEventLogRecordV3,
    MiniJournalBoundaryTypeV3,
    MiniJournalRecordV3,
    ThreadRoleV3,
    ThreadSnapshotV3,
    ThreadActorModeV3,
    copy_snapshot_v3,
    normalize_thread_snapshot_v3,
)
from backend.conversation.projector.thread_event_projector_runtime_v3 import (
    apply_lifecycle_v3,
    apply_reset_v3,
    patch_item_v3,
    upsert_item_v3,
)
from backend.conversation.projector.thread_event_projector_v3 import project_v2_snapshot_to_v3
from backend.conversation.services.thread_actor_runtime_v3 import ThreadActorRuntimeV3
from backend.conversation.services.thread_checkpoint_policy_v3 import ThreadCheckpointPolicyV3
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_replay_buffer_service_v3 import ThreadReplayBufferServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.storage.thread_event_log_store_v3 import ThreadEventLogStoreV3
from backend.conversation.storage.thread_mini_journal_store_v3 import ThreadMiniJournalStoreV3
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.conversation.storage.thread_snapshot_store_v3 import ThreadSnapshotStoreV3
from backend.errors.app_errors import ConversationStreamMismatch, ConversationV3Missing
from backend.storage.file_utils import iso_now
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_MAX_TERMINAL_LIFECYCLE_GUARD_ENTRIES = 128


class ThreadQueryServiceV3:
    def __init__(
        self,
        *,
        storage: Any,
        chat_service: Any,
        thread_lineage_service: Any | None,
        codex_client: Any,
        snapshot_store_v3: ThreadSnapshotStoreV3,
        snapshot_store_v2: ThreadSnapshotStoreV2,
        registry_service_v2: ThreadRegistryService,
        request_ledger_service: RequestLedgerServiceV3,
        thread_event_broker: ChatEventBroker,
        replay_buffer_service: ThreadReplayBufferServiceV3 | None = None,
        mini_journal_store_v3: ThreadMiniJournalStoreV3 | None = None,
        event_log_store_v3: ThreadEventLogStoreV3 | None = None,
        checkpoint_policy_v3: ThreadCheckpointPolicyV3 | None = None,
        actor_runtime_v3: ThreadActorRuntimeV3 | None = None,
        thread_actor_mode: ThreadActorModeV3 | str | None = None,
        log_compact_min_events: int = 200,
    ) -> None:
        self._storage = storage
        self._chat_service = chat_service
        self._thread_lineage_service = thread_lineage_service
        self._codex_client = codex_client
        self._snapshot_store_v3 = snapshot_store_v3
        self._snapshot_store_v2 = snapshot_store_v2
        self._registry_service_v2 = registry_service_v2
        self._request_ledger_service = request_ledger_service
        self._thread_event_broker = thread_event_broker
        self._replay_buffer_service = replay_buffer_service
        resolved_mode = str(thread_actor_mode or get_thread_actor_mode()).strip().lower()
        if resolved_mode not in {"off", "shadow", "on"}:
            resolved_mode = "off"
        self._thread_actor_mode: ThreadActorModeV3 = resolved_mode  # type: ignore[assignment]
        self._mini_journal_store_v3 = mini_journal_store_v3
        self._event_log_store_v3 = event_log_store_v3
        self._log_compact_min_events = max(1, int(log_compact_min_events))
        self._checkpoint_policy_v3 = checkpoint_policy_v3 or ThreadCheckpointPolicyV3()
        self._actor_runtime_v3 = actor_runtime_v3 or ThreadActorRuntimeV3()
        self._lifecycle_guard_lock = threading.Lock()
        self._last_lifecycle_signature_by_thread: dict[
            tuple[str, str, str, str],
            tuple[str, str, str | None, str | None],
        ] = {}
        self._terminal_lifecycle_signature_by_turn: dict[
            tuple[str, str, str, str],
            dict[str, tuple[str, str, str | None, str | None]],
        ] = {}

    def issue_stream_event_id(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str | None,
    ) -> str:
        with self._storage.project_lock(project_id):
            return self._registry_service_v2.issue_next_event_id(
                project_id,
                node_id,
                thread_role,
                thread_id=thread_id,
            )

    def _resolve_stream_thread_id(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
    ) -> str:
        thread_id = str(snapshot.get("threadId") or "").strip()
        if thread_id:
            return thread_id
        entry = self._registry_service_v2.read_entry(project_id, node_id, thread_role)
        entry_thread_id = str(entry.get("threadId") or "").strip()
        if entry_thread_id:
            return entry_thread_id
        cursor_thread_id = str(entry.get("eventCursorThreadId") or "").strip()
        if cursor_thread_id:
            return cursor_thread_id
        return f"unbound::{thread_role}"

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _is_actor_mode_on(self) -> bool:
        return self._thread_actor_mode == "on"

    def _is_actor_mode_shadow(self) -> bool:
        return self._thread_actor_mode == "shadow"

    def _is_actor_mode_active(self) -> bool:
        return self._thread_actor_mode in {"shadow", "on"}

    @staticmethod
    def _parse_event_id(envelope: dict[str, Any]) -> int | None:
        raw = str(envelope.get("event_id") or envelope.get("eventId") or "").strip()
        if not raw.isdigit():
            return None
        return int(raw)

    @classmethod
    def _event_id_range(cls, envelopes: list[dict[str, Any]]) -> tuple[int | None, int | None]:
        parsed = [event_id for event_id in (cls._parse_event_id(envelope) for envelope in envelopes) if event_id is not None]
        if not parsed:
            return None, None
        return min(parsed), max(parsed)

    @staticmethod
    def _boundary_from_events(events: list[dict[str, Any]]) -> MiniJournalBoundaryTypeV3 | None:
        resolved: MiniJournalBoundaryTypeV3 | None = None
        for event in events:
            if str(event.get("type") or "").strip() != event_types.THREAD_LIFECYCLE_V3:
                continue
            payload = event.get("payload", {})
            if not isinstance(payload, dict):
                continue
            state = str(payload.get("state") or "").strip()
            if state == event_types.TURN_COMPLETED:
                resolved = "turn_completed"
            elif state == event_types.TURN_FAILED:
                resolved = "turn_failed"
            elif state == event_types.WAITING_USER_INPUT:
                resolved = "waiting_user_input"
        return resolved

    @staticmethod
    def _record_boundary_type(value: str) -> MiniJournalBoundaryTypeV3:
        normalized = str(value or "").strip()
        if normalized not in MINI_JOURNAL_BOUNDARY_TYPES_V3:
            raise ValueError(f"Invalid mini-journal boundary type: {normalized!r}")
        return normalized  # type: ignore[return-value]

    def _validate_recovery_tail(
        self,
        records: list[MiniJournalRecordV3],
        *,
        snapshot_version: int,
    ) -> None:
        if not records:
            return
        last_seq = 0
        for record in records:
            seq = int(record.get("journalSeq") or 0)
            event_start = int(record.get("eventIdStart") or 0)
            event_end = int(record.get("eventIdEnd") or 0)
            if seq <= 0:
                raise ValueError("Mini-journal recovery validation failed: journalSeq must be > 0.")
            if event_start > event_end:
                raise ValueError("Mini-journal recovery validation failed: eventIdStart > eventIdEnd.")
            if last_seq and seq != last_seq + 1:
                raise ValueError(
                    f"Mini-journal recovery validation failed: journalSeq gap detected ({last_seq} -> {seq})."
                )
            last_seq = seq

        pending_after_snapshot = [
            record for record in records if int(record.get("snapshotVersionAtWrite") or 0) > int(snapshot_version)
        ]
        if pending_after_snapshot:
            first_pending = pending_after_snapshot[0]
            raise ValueError(
                "Mini-journal recovery validation failed: journal tail indicates pending boundaries after snapshot "
                f"(journalSeq={first_pending.get('journalSeq')}, snapshotVersionAtWrite={first_pending.get('snapshotVersionAtWrite')}, snapshotVersion={snapshot_version})."
            )

    def _validate_event_log_tail(
        self,
        records: list[ThreadEventLogRecordV3],
    ) -> None:
        if not records:
            return
        last_seq = 0
        last_event_id = 0
        for record in records:
            seq = int(record.get("logSeq") or 0)
            event_id = int(record.get("eventId") or 0)
            payload = record.get("payload")
            if seq <= 0:
                raise ValueError("Thread event-log recovery validation failed: logSeq must be > 0.")
            if event_id <= 0:
                raise ValueError("Thread event-log recovery validation failed: eventId must be > 0.")
            if not isinstance(payload, dict):
                raise ValueError("Thread event-log recovery validation failed: payload must be an object.")
            if last_seq and seq != last_seq + 1:
                raise ValueError(
                    f"Thread event-log recovery validation failed: logSeq gap detected ({last_seq} -> {seq})."
                )
            if last_event_id and event_id <= last_event_id:
                raise ValueError(
                    "Thread event-log recovery validation failed: non-monotonic eventId sequence "
                    f"({last_event_id} -> {event_id})."
                )
            last_seq = seq
            last_event_id = event_id

    def _apply_event_log_envelope_to_snapshot(
        self,
        snapshot: ThreadSnapshotV3,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        envelope: dict[str, Any],
    ) -> ThreadSnapshotV3:
        event_type = str(envelope.get("event_type") or envelope.get("type") or "").strip()
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        updated = copy_snapshot_v3(snapshot)
        try:
            if event_type == event_types.THREAD_SNAPSHOT_V3:
                replay_snapshot = payload.get("snapshot")
                if not isinstance(replay_snapshot, dict):
                    raise ValueError("Thread event-log replay failed: snapshot payload is missing.")
                updated = normalize_thread_snapshot_v3(
                    replay_snapshot,
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                )
            elif event_type == event_types.CONVERSATION_ITEM_UPSERT_V3:
                item = payload.get("item")
                if not isinstance(item, dict):
                    raise ValueError("Thread event-log replay failed: upsert payload.item is missing.")
                updated, _ = upsert_item_v3(updated, item)
            elif event_type == event_types.CONVERSATION_ITEM_PATCH_V3:
                item_id = str(payload.get("itemId") or "").strip()
                patch = payload.get("patch")
                if not item_id or not isinstance(patch, dict):
                    raise ValueError("Thread event-log replay failed: patch payload is invalid.")
                updated, _ = patch_item_v3(updated, item_id, patch)
            elif event_type == event_types.THREAD_LIFECYCLE_V3:
                lifecycle_state = str(payload.get("state") or "").strip()
                if not lifecycle_state:
                    raise ValueError("Thread event-log replay failed: lifecycle payload.state is missing.")
                processing_state = str(payload.get("processingState") or updated.get("processingState") or "").strip()
                active_turn_id = self._normalize_optional_string(payload.get("activeTurnId"))
                detail = self._normalize_optional_string(payload.get("detail"))
                updated, _ = apply_lifecycle_v3(
                    updated,
                    state=lifecycle_state,
                    processing_state=processing_state,
                    active_turn_id=active_turn_id,
                    detail=detail,
                )
            elif event_type == event_types.CONVERSATION_UI_PLAN_READY_V3:
                plan_ready = payload.get("planReady")
                if not isinstance(plan_ready, dict):
                    raise ValueError("Thread event-log replay failed: planReady payload is invalid.")
                updated["uiSignals"]["planReady"] = copy.deepcopy(plan_ready)
            elif event_type == event_types.CONVERSATION_UI_USER_INPUT_V3:
                active_requests = payload.get("activeUserInputRequests")
                if not isinstance(active_requests, list):
                    raise ValueError("Thread event-log replay failed: activeUserInputRequests payload is invalid.")
                updated["uiSignals"]["activeUserInputRequests"] = copy.deepcopy(active_requests)
            elif event_type == event_types.THREAD_ERROR_V3:
                error_item = payload.get("errorItem")
                if not isinstance(error_item, dict):
                    raise ValueError("Thread event-log replay failed: errorItem payload is missing.")
                updated, _ = upsert_item_v3(updated, error_item)
            else:
                raise ValueError(f"Thread event-log replay failed: unsupported event_type '{event_type}'.")
        except ConversationStreamMismatch as exc:
            raise ValueError("Thread event-log replay failed: envelope violates stream invariants.") from exc

        event_snapshot_version = int(
            envelope.get("snapshotVersion") or envelope.get("snapshot_version") or updated.get("snapshotVersion") or 0
        )
        if event_snapshot_version < int(snapshot.get("snapshotVersion") or 0):
            raise ValueError(
                "Thread event-log replay failed: snapshot version regression detected "
                f"({snapshot.get('snapshotVersion')} -> {event_snapshot_version})."
            )
        updated["snapshotVersion"] = max(event_snapshot_version, int(updated.get("snapshotVersion") or 0))
        updated["updatedAt"] = iso_now()
        return updated

    def _recover_snapshot_from_event_log_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
    ) -> tuple[ThreadSnapshotV3, int]:
        if self._event_log_store_v3 is None:
            return snapshot, 0
        all_records = self._event_log_store_v3.read_tail_after_log_seq(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
            cursor=0,
        )
        self._validate_event_log_tail(all_records)
        if not all_records:
            return snapshot, 0

        recovered = copy_snapshot_v3(snapshot)
        snapshot_version = int(recovered.get("snapshotVersion") or 0)
        pending_records = [
            record for record in all_records if int(record.get("snapshotVersionAtAppend") or 0) > snapshot_version
        ]
        for record in pending_records:
            payload = record.get("payload")
            envelope = payload if isinstance(payload, dict) else {}
            recovered = self._apply_event_log_envelope_to_snapshot(
                recovered,
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                envelope=envelope,
            )

        return recovered, int(all_records[-1].get("logSeq") or 0)

    def _append_event_log_tail_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
        envelopes: list[dict[str, Any]],
    ) -> None:
        if self._event_log_store_v3 is None or not envelopes:
            return
        next_seq = self._event_log_store_v3.latest_log_seq(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
        ) + 1
        snapshot_version = int(snapshot.get("snapshotVersion") or 0)
        for envelope in envelopes:
            event_id = self._parse_event_id(envelope)
            if event_id is None or event_id <= 0:
                continue
            record: ThreadEventLogRecordV3 = {
                "logSeq": next_seq,
                "projectId": str(project_id or "").strip(),
                "nodeId": str(node_id or "").strip(),
                "threadRole": str(thread_role or "").strip(),
                "threadId": str(thread_id or "").strip(),
                "eventId": int(event_id),
                "snapshotVersionAtAppend": snapshot_version,
                "payload": copy.deepcopy(envelope),
                "createdAt": iso_now(),
            }
            self._event_log_store_v3.append_event_record(
                project_id,
                node_id,
                thread_role,
                record,
            )
            next_seq += 1

    def _compact_event_log_after_checkpoint_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        event_id_cursor: int,
    ) -> None:
        if self._event_log_store_v3 is None or event_id_cursor <= 0:
            return
        count = self._event_log_store_v3.count_entries(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
        )
        if count < self._log_compact_min_events:
            return
        self._event_log_store_v3.prune_before_event_id(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
            event_id=event_id_cursor,
        )

    def _bootstrap_actor_from_snapshot_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
    ) -> ThreadSnapshotV3:
        resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, snapshot)
        if not resolved_thread_id:
            return snapshot
        if self._actor_runtime_v3.has_actor(project_id, node_id, thread_role, resolved_thread_id):
            actor_snapshot = self._actor_runtime_v3.get_actor_snapshot(project_id, node_id, thread_role, resolved_thread_id)
            if actor_snapshot is not None:
                return actor_snapshot
            return snapshot

        recovered_snapshot = copy_snapshot_v3(snapshot)
        last_journal_seq = 0
        if self._mini_journal_store_v3 is not None:
            recovery_tail = self._mini_journal_store_v3.read_tail_after(
                project_id,
                node_id,
                thread_role,
                thread_id=resolved_thread_id,
                cursor=0,
            )
            self._validate_recovery_tail(
                recovery_tail,
                snapshot_version=int(recovered_snapshot.get("snapshotVersion") or 0),
            )
            if recovery_tail:
                last_journal_seq = int(recovery_tail[-1].get("journalSeq") or 0)

        recovered_snapshot, _ = self._recover_snapshot_from_event_log_locked(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=resolved_thread_id,
            snapshot=recovered_snapshot,
        )

        self._actor_runtime_v3.bootstrap_actor(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=resolved_thread_id,
            snapshot=recovered_snapshot,
            last_journal_seq=last_journal_seq,
        )
        actor_snapshot = self._actor_runtime_v3.get_actor_snapshot(project_id, node_id, thread_role, resolved_thread_id)
        return actor_snapshot or recovered_snapshot

    def _checkpoint_actor_if_needed_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        boundary_type: MiniJournalBoundaryTypeV3 | None,
    ) -> ThreadSnapshotV3 | None:
        stats = self._actor_runtime_v3.checkpoint_stats(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=thread_id,
        )
        if not bool(stats.get("exists")):
            return None

        elapsed_ms = int(stats.get("elapsed_ms") or 0)
        dirty_events_count = int(stats.get("dirty_events_count") or 0)
        resolved_boundary = str(boundary_type or "").strip()
        should_checkpoint = self._checkpoint_policy_v3.should_checkpoint(
            resolved_boundary or None,
            elapsed_ms,
            dirty_events_count,
        )
        if not should_checkpoint:
            return None

        snapshot = stats.get("snapshot")
        if not isinstance(snapshot, dict):
            return None
        snapshot_copy = copy_snapshot_v3(snapshot)  # type: ignore[arg-type]
        event_start = int(stats.get("dirty_event_start") or 0)
        event_end = int(stats.get("dirty_event_end") or 0)
        if dirty_events_count <= 0:
            event_start = 0
            event_end = 0
        elif event_start > event_end:
            raise ValueError("Actor checkpoint failed: dirty event range is invalid.")

        next_seq = int(stats.get("last_journal_seq") or 0) + 1
        journal_boundary = self._record_boundary_type(resolved_boundary or "timer_checkpoint")

        if self._mini_journal_store_v3 is not None:
            record: MiniJournalRecordV3 = {
                "journalSeq": next_seq,
                "projectId": str(project_id or "").strip(),
                "nodeId": str(node_id or "").strip(),
                "threadRole": str(thread_role or "").strip(),
                "threadId": str(thread_id or "").strip(),
                "turnId": self._normalize_optional_string(snapshot_copy.get("activeTurnId")),
                "eventIdStart": event_start,
                "eventIdEnd": event_end,
                "boundaryType": journal_boundary,
                "snapshotVersionAtWrite": int(snapshot_copy.get("snapshotVersion") or 0),
                "createdAt": iso_now(),
            }
            self._mini_journal_store_v3.append_boundary_record(
                project_id,
                node_id,
                thread_role,
                record,
            )

        checkpointed = self.write_snapshot_checkpoint(
            project_id,
            node_id,
            thread_role,
            snapshot_copy,
        )
        self._actor_runtime_v3.mark_checkpoint_committed(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=thread_id,
            snapshot=checkpointed,
            journal_seq=next_seq,
        )
        if dirty_events_count > 0 and event_end > 0:
            try:
                self._compact_event_log_after_checkpoint_locked(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    thread_id=thread_id,
                    event_id_cursor=event_end,
                )
            except Exception:
                logger.warning(
                    "Thread event-log compaction skipped after checkpoint for %s/%s/%s (thread_id=%s).",
                    project_id,
                    node_id,
                    thread_role,
                    thread_id,
                    exc_info=True,
                )
        return checkpointed

    def _lifecycle_signature_from_envelope(
        self,
        envelope: dict[str, Any],
    ) -> tuple[str, str, str | None, str | None] | None:
        event_type = str(envelope.get("event_type") or envelope.get("type") or "").strip()
        if event_type != event_types.THREAD_LIFECYCLE_V3:
            return None
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            return None
        state = str(payload.get("state") or "").strip()
        processing_state = str(payload.get("processingState") or "").strip()
        active_turn_id = self._normalize_optional_string(payload.get("activeTurnId"))
        detail = self._normalize_optional_string(payload.get("detail"))
        return (state, processing_state, active_turn_id, detail)

    @staticmethod
    def _is_terminal_lifecycle_state(state: str) -> bool:
        return state in {event_types.TURN_COMPLETED, event_types.TURN_FAILED}

    def _should_suppress_lifecycle_publish(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        envelope: dict[str, Any],
    ) -> bool:
        signature = self._lifecycle_signature_from_envelope(envelope)
        if signature is None:
            return False
        state, _, active_turn_id, _ = signature
        envelope_turn_id = self._normalize_optional_string(envelope.get("turn_id") or envelope.get("turnId"))
        turn_id = envelope_turn_id or active_turn_id
        key = (
            str(project_id or "").strip(),
            str(node_id or "").strip(),
            str(thread_role or "").strip(),
            str(thread_id or "").strip(),
        )

        with self._lifecycle_guard_lock:
            previous_signature = self._last_lifecycle_signature_by_thread.get(key)
            if previous_signature == signature:
                return True

            if turn_id is not None and self._is_terminal_lifecycle_state(state):
                by_turn = self._terminal_lifecycle_signature_by_turn.setdefault(key, {})
                if by_turn.get(turn_id) == signature:
                    self._last_lifecycle_signature_by_thread[key] = signature
                    return True
                by_turn[turn_id] = signature
                while len(by_turn) > _MAX_TERMINAL_LIFECYCLE_GUARD_ENTRIES:
                    oldest_turn_id = next(iter(by_turn))
                    by_turn.pop(oldest_turn_id, None)

            self._last_lifecycle_signature_by_thread[key] = signature
            return False

    def _publish_thread_envelope(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        envelope: dict[str, Any],
    ) -> None:
        if self._should_suppress_lifecycle_publish(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=thread_id,
            envelope=envelope,
        ):
            return
        if self._replay_buffer_service is not None:
            self._replay_buffer_service.append_business_event(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                thread_id=thread_id,
                envelope=envelope,
            )
        self._thread_event_broker.publish(project_id, node_id, envelope, thread_role=thread_role)

    def get_thread_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        publish_repairs: bool = True,
        ensure_binding: bool = True,
    ) -> ThreadSnapshotV3:
        self._chat_service._validate_thread_access(project_id, node_id, thread_role)
        session = None
        if thread_role == "ask_planning":
            session = self._chat_service.get_session(project_id, node_id, thread_role=thread_role)
        elif ensure_binding and self._thread_lineage_service is not None:
            workspace_root = self._chat_service._workspace_root_for_project(project_id)
            self._thread_lineage_service.ensure_thread_binding_v2(
                project_id,
                node_id,
                thread_role,
                workspace_root,
            )

        with self._storage.project_lock(project_id):
            updated, changed = self._load_or_bridge_snapshot_locked(
                project_id,
                node_id,
                thread_role,
                session=session,
            )
            stale_checked, stale_changed = self._request_ledger_service.mark_stale_missing_runtime_requests(
                updated,
                runtime_request_exists=lambda request_id: self._codex_client.get_runtime_request(request_id) is not None,
            )
            updated = stale_checked
            changed = changed or stale_changed

            if not changed:
                if self._is_actor_mode_on():
                    return self._bootstrap_actor_from_snapshot_locked(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role=thread_role,
                        snapshot=updated,
                    )
                return updated

            updated["snapshotVersion"] = int(updated.get("snapshotVersion") or 0) + 1
            updated["updatedAt"] = iso_now()
            updated = self._snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, updated)
            if publish_repairs:
                resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, updated)
                event_id = self._registry_service_v2.issue_next_event_id(
                    project_id,
                    node_id,
                    thread_role,
                    thread_id=resolved_thread_id,
                )
                envelope = build_thread_envelope(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    snapshot_version=updated["snapshotVersion"],
                    event_type=event_types.THREAD_SNAPSHOT_V3,
                    payload={"snapshot": updated},
                    event_id=event_id,
                    thread_id=resolved_thread_id,
                )
                self._publish_thread_envelope(
                    project_id,
                    node_id,
                    thread_role,
                    resolved_thread_id,
                    envelope,
                )
            if self._is_actor_mode_on():
                return self._bootstrap_actor_from_snapshot_locked(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    snapshot=updated,
                )
            return updated

    def _load_or_bridge_snapshot_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        session: dict[str, Any] | None,
    ) -> tuple[ThreadSnapshotV3, bool]:
        if self._snapshot_store_v3.exists(project_id, node_id, thread_role):
            snapshot = self._snapshot_store_v3.read_snapshot(project_id, node_id, thread_role)
            return self._reconcile_snapshot_locked(
                project_id,
                node_id,
                thread_role,
                snapshot=snapshot,
                session=session,
                changed=False,
            )

        bridge_mode = get_conversation_v3_bridge_mode()
        if not is_conversation_v3_bridge_allowed_for_project(project_id):
            logger.debug(
                "V3 snapshot missing for %s/%s/%s and bridge mode %s denies fallback.",
                project_id,
                node_id,
                thread_role,
                bridge_mode,
            )
            raise ConversationV3Missing()

        snapshot_v2 = self._snapshot_store_v2.read_snapshot(project_id, node_id, thread_role)
        bridged = normalize_thread_snapshot_v3(
            project_v2_snapshot_to_v3(snapshot_v2),
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
        )
        return self._reconcile_snapshot_locked(
            project_id,
            node_id,
            thread_role,
            snapshot=bridged,
            session=session,
            changed=True,
        )

    def _reconcile_snapshot_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        snapshot: ThreadSnapshotV3,
        session: dict[str, Any] | None,
        changed: bool,
    ) -> tuple[ThreadSnapshotV3, bool]:
        updated = copy_snapshot_v3(snapshot)
        if session is not None:
            registry, _ = self._registry_service_v2.seed_from_legacy_session(
                project_id,
                node_id,
                thread_role,
                session,
            )
        else:
            registry = self._registry_service_v2.read_entry(project_id, node_id, thread_role)

        registry_thread_id = str(registry.get("threadId") or "").strip() or None
        if updated.get("threadId") != registry_thread_id:
            updated["threadId"] = registry_thread_id
            changed = True

        if session is not None:
            legacy_active_turn = str(session.get("active_turn_id") or "").strip() or None
            if updated.get("activeTurnId") != legacy_active_turn:
                updated["activeTurnId"] = legacy_active_turn
                if legacy_active_turn:
                    updated["processingState"] = "running"
                elif updated.get("processingState") == "running":
                    updated["processingState"] = "idle"
                changed = True

        normalized = normalize_thread_snapshot_v3(
            updated,
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
        )
        if normalized != snapshot:
            changed = True
        return normalized, changed

    def _persist_thread_mutation_legacy_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        updated = copy_snapshot_v3(snapshot)
        updated["snapshotVersion"] = int(updated.get("snapshotVersion") or 0) + 1
        updated["updatedAt"] = iso_now()
        updated = self._snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, updated)
        resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, updated)
        envelopes: list[dict[str, Any]] = []
        for event in events:
            payload = event.get("payload", {})
            if event.get("type") == event_types.THREAD_SNAPSHOT_V3:
                payload = {"snapshot": updated}
            event_id = self._registry_service_v2.issue_next_event_id(
                project_id,
                node_id,
                thread_role,
                thread_id=resolved_thread_id,
            )
            envelope = build_thread_envelope(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                snapshot_version=updated["snapshotVersion"],
                event_type=str(event.get("type") or ""),
                payload=payload if isinstance(payload, dict) else {},
                event_id=event_id,
                thread_id=resolved_thread_id,
            )
            envelopes.append(envelope)
            self._publish_thread_envelope(
                project_id,
                node_id,
                thread_role,
                resolved_thread_id,
                envelope,
            )
        return updated, envelopes

    def publish_mutation_events(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        with self._storage.project_lock(project_id):
            updated = copy_snapshot_v3(snapshot)
            updated["snapshotVersion"] = int(updated.get("snapshotVersion") or 0) + 1
            updated["updatedAt"] = iso_now()
            resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, updated)
            envelopes: list[dict[str, Any]] = []
            for event in events:
                payload = event.get("payload", {})
                if event.get("type") == event_types.THREAD_SNAPSHOT_V3:
                    payload = {"snapshot": updated}
                event_id = self._registry_service_v2.issue_next_event_id(
                    project_id,
                    node_id,
                    thread_role,
                    thread_id=resolved_thread_id,
                )
                envelope = build_thread_envelope(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    snapshot_version=updated["snapshotVersion"],
                    event_type=str(event.get("type") or ""),
                    payload=payload if isinstance(payload, dict) else {},
                    event_id=event_id,
                    thread_id=resolved_thread_id,
                )
                envelopes.append(envelope)
                self._publish_thread_envelope(
                    project_id,
                    node_id,
                    thread_role,
                    resolved_thread_id,
                    envelope,
                )
            return updated, envelopes

    def write_snapshot_checkpoint(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
    ) -> ThreadSnapshotV3:
        with self._storage.project_lock(project_id):
            updated = copy_snapshot_v3(snapshot)
            updated["updatedAt"] = iso_now()
            return self._snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, updated)

    def _persist_thread_mutation_actor_on_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        self._bootstrap_actor_from_snapshot_locked(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=snapshot,
        )
        updated, envelopes = self.publish_mutation_events(
            project_id,
            node_id,
            thread_role,
            snapshot,
            events,
        )
        resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, updated)
        self._append_event_log_tail_locked(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=resolved_thread_id,
            snapshot=updated,
            envelopes=envelopes,
        )
        self._actor_runtime_v3.apply_events(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=resolved_thread_id,
            snapshot=updated,
            envelopes=envelopes,
        )
        boundary_type = self._boundary_from_events(events)
        checkpointed = self._checkpoint_actor_if_needed_locked(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=resolved_thread_id,
            boundary_type=boundary_type,
        )
        if checkpointed is not None:
            return checkpointed, envelopes
        actor_snapshot = self._actor_runtime_v3.get_actor_snapshot(
            project_id,
            node_id,
            thread_role,
            resolved_thread_id,
        )
        return actor_snapshot or updated, envelopes

    def _persist_thread_mutation_shadow_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        updated, envelopes = self._persist_thread_mutation_legacy_locked(
            project_id,
            node_id,
            thread_role,
            snapshot,
            events,
        )
        try:
            resolved_thread_id = self._resolve_stream_thread_id(project_id, node_id, thread_role, updated)
            self._actor_runtime_v3.bootstrap_actor(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                thread_id=resolved_thread_id,
                snapshot=snapshot,
            )
            self._actor_runtime_v3.apply_events(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                thread_id=resolved_thread_id,
                snapshot=updated,
                envelopes=envelopes,
            )
            boundary_type = self._boundary_from_events(events)
            if boundary_type is not None:
                signatures_match = self._actor_runtime_v3.compare_actor_snapshot_signature(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    thread_id=resolved_thread_id,
                    snapshot=updated,
                )
                if not signatures_match:
                    logger.warning(
                        "Thread actor shadow mismatch for %s/%s/%s (thread_id=%s).",
                        project_id,
                        node_id,
                        thread_role,
                        resolved_thread_id,
                    )
        except Exception:
            logger.debug(
                "Thread actor shadow apply failed for %s/%s/%s.",
                project_id,
                node_id,
                thread_role,
                exc_info=True,
            )
        return updated, envelopes

    def persist_thread_mutation(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        with self._storage.project_lock(project_id):
            if self._is_actor_mode_on():
                return self._persist_thread_mutation_actor_on_locked(
                    project_id,
                    node_id,
                    thread_role,
                    snapshot,
                    events,
                )
            if self._is_actor_mode_shadow():
                return self._persist_thread_mutation_shadow_locked(
                    project_id,
                    node_id,
                    thread_role,
                    snapshot,
                    events,
                )
            return self._persist_thread_mutation_legacy_locked(
                project_id,
                node_id,
                thread_role,
                snapshot,
                events,
            )

    def reset_thread(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> ThreadSnapshotV3:
        self._chat_service.reset_session(project_id, node_id, thread_role=thread_role)
        with self._storage.project_lock(project_id):
            self._registry_service_v2.clear_entry(project_id, node_id, thread_role)
            snapshot = self._snapshot_store_v3.read_snapshot(project_id, node_id, thread_role)
            reset_snapshot, events = apply_reset_v3(snapshot)
            reset_snapshot["threadId"] = None
        updated, _ = self.persist_thread_mutation(project_id, node_id, thread_role, reset_snapshot, events)
        if self._is_actor_mode_active():
            thread_id = str(snapshot.get("threadId") or "").strip()
            if thread_id:
                try:
                    self._checkpoint_actor_if_needed_locked(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role=thread_role,
                        thread_id=thread_id,
                        boundary_type="eviction",
                    )
                finally:
                    self._actor_runtime_v3.evict_actor(project_id, node_id, thread_role, thread_id)
        return updated

    def build_stream_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        after_snapshot_version: int | None,
        ensure_binding: bool = True,
    ) -> ThreadSnapshotV3:
        snapshot = self.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=ensure_binding,
        )
        if after_snapshot_version is not None and int(after_snapshot_version) > int(snapshot.get("snapshotVersion") or 0):
            raise ConversationStreamMismatch()
        return snapshot
