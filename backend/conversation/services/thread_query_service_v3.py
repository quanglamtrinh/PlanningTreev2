from __future__ import annotations

import logging
import threading
from typing import Any

from backend.config.app_config import (
    get_conversation_v3_bridge_mode,
    is_conversation_v3_bridge_allowed_for_project,
)
from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.conversation.domain.types_v3 import (
    ThreadRoleV3,
    ThreadSnapshotV3,
    copy_snapshot_v3,
    normalize_thread_snapshot_v3,
)
from backend.conversation.projector.thread_event_projector_runtime_v3 import apply_reset_v3
from backend.conversation.projector.thread_event_projector_v3 import project_v2_snapshot_to_v3
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_replay_buffer_service_v3 import ThreadReplayBufferServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
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

    def persist_thread_mutation(
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

    def reset_thread(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> ThreadSnapshotV3:
        self._chat_service.reset_session(project_id, node_id, thread_role=thread_role)
        with self._storage.project_lock(project_id):
            self._registry_service_v2.clear_entry(project_id, node_id, thread_role)
            snapshot = self._snapshot_store_v3.read_snapshot(project_id, node_id, thread_role)
            reset_snapshot, events = apply_reset_v3(snapshot)
            reset_snapshot["threadId"] = None
        updated, _ = self.persist_thread_mutation(project_id, node_id, thread_role, reset_snapshot, events)
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
