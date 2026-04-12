from __future__ import annotations

import logging
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
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.conversation.storage.thread_snapshot_store_v3 import ThreadSnapshotStoreV3
from backend.errors.app_errors import ConversationStreamMismatch, ConversationV3Missing
from backend.storage.file_utils import iso_now
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)


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
                self._thread_event_broker.publish(project_id, node_id, envelope, thread_role=thread_role)
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
                self._thread_event_broker.publish(project_id, node_id, envelope, thread_role=thread_role)
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
