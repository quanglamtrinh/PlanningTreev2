from __future__ import annotations

from typing import Any

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.conversation.domain.types import ThreadRole, ThreadSnapshotV2, copy_snapshot, next_snapshot_version, snapshot_with_metadata
from backend.conversation.projector.thread_event_projector import apply_reset, build_snapshot_event
from backend.conversation.services.request_ledger_service import RequestLedgerService
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.storage.file_utils import iso_now
from backend.streaming.sse_broker import ChatEventBroker


class ThreadQueryService:
    def __init__(
        self,
        *,
        storage: Any,
        chat_service: Any,
        codex_client: Any,
        snapshot_store: ThreadSnapshotStoreV2,
        registry_service: ThreadRegistryService,
        request_ledger_service: RequestLedgerService,
        thread_event_broker: ChatEventBroker,
    ) -> None:
        self._storage = storage
        self._chat_service = chat_service
        self._codex_client = codex_client
        self._snapshot_store = snapshot_store
        self._registry_service = registry_service
        self._request_ledger_service = request_ledger_service
        self._thread_event_broker = thread_event_broker

    def get_thread_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        *,
        publish_repairs: bool = True,
    ) -> ThreadSnapshotV2:
        self._chat_service._validate_thread_access(project_id, node_id, thread_role)
        session = self._chat_service.get_session(project_id, node_id, thread_role=thread_role)
        with self._storage.project_lock(project_id):
            snapshot = self._snapshot_store.read_snapshot(project_id, node_id, thread_role)
            registry, registry_changed = self._registry_service.seed_from_legacy_session(
                project_id,
                node_id,
                thread_role,
                session,
            )
            updated = snapshot_with_metadata(snapshot, registry)
            changed = registry_changed or updated != snapshot or not self._snapshot_store.exists(project_id, node_id, thread_role)

            legacy_active_turn = str(session.get("active_turn_id") or "").strip() or None
            if updated.get("activeTurnId") != legacy_active_turn:
                updated["activeTurnId"] = legacy_active_turn
                if legacy_active_turn:
                    updated["processingState"] = "running"
                elif updated.get("processingState") == "running":
                    updated["processingState"] = "idle"
                changed = True

            stale_checked, stale_changed = self._request_ledger_service.mark_stale_missing_runtime_requests(
                updated,
                runtime_request_exists=lambda request_id: self._codex_client.get_runtime_request(request_id) is not None,
            )
            updated = stale_checked
            changed = changed or stale_changed

            if not changed:
                return updated

            updated["snapshotVersion"] = next_snapshot_version(updated)
            updated["updatedAt"] = iso_now()
            updated = self._snapshot_store.write_snapshot(project_id, node_id, thread_role, updated)
            if publish_repairs:
                envelope = build_thread_envelope(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    snapshot_version=updated["snapshotVersion"],
                    event_type=event_types.THREAD_SNAPSHOT,
                    payload={"snapshot": updated},
                )
                self._thread_event_broker.publish(project_id, node_id, envelope, thread_role=thread_role)
            return updated

    def persist_thread_mutation(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        snapshot: ThreadSnapshotV2,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
        with self._storage.project_lock(project_id):
            updated = copy_snapshot(snapshot)
            updated["snapshotVersion"] = next_snapshot_version(updated)
            updated["updatedAt"] = iso_now()
            updated = self._snapshot_store.write_snapshot(project_id, node_id, thread_role, updated)
            envelopes: list[dict[str, Any]] = []
            for event in events:
                payload = copy_snapshot(updated) if event.get("type") == event_types.THREAD_SNAPSHOT else event.get("payload", {})
                if event.get("type") == event_types.THREAD_SNAPSHOT:
                    payload = {"snapshot": updated}
                envelope = build_thread_envelope(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    snapshot_version=updated["snapshotVersion"],
                    event_type=str(event.get("type") or ""),
                    payload=payload,
                )
                envelopes.append(envelope)
                self._thread_event_broker.publish(project_id, node_id, envelope, thread_role=thread_role)
            return updated, envelopes

    def reset_thread(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadSnapshotV2:
        self._chat_service.reset_session(project_id, node_id, thread_role=thread_role)
        with self._storage.project_lock(project_id):
            self._registry_service.clear_entry(project_id, node_id, thread_role)
            snapshot = self._snapshot_store.read_snapshot(project_id, node_id, thread_role)
            reset_snapshot, events = apply_reset(snapshot)
            reset_snapshot["threadId"] = None
            reset_snapshot["lineage"] = {
                "forkedFromThreadId": None,
                "forkedFromNodeId": None,
                "forkedFromRole": None,
                "forkReason": None,
                "lineageRootThreadId": None,
            }
        updated, _ = self.persist_thread_mutation(project_id, node_id, thread_role, reset_snapshot, events)
        return updated

    def sync_legacy_turn_state(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        *,
        thread_id: str | None,
        active_turn_id: str | None,
    ) -> None:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)
            session["thread_id"] = thread_id
            session["active_turn_id"] = active_turn_id
            self._storage.chat_state_store.write_session(project_id, node_id, session, thread_role=thread_role)

    def clear_legacy_turn_state(self, project_id: str, node_id: str, thread_role: ThreadRole, *, thread_id: str | None) -> None:
        self.sync_legacy_turn_state(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
            active_turn_id=None,
        )

    def build_stream_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        *,
        after_snapshot_version: int | None,
    ) -> ThreadSnapshotV2:
        snapshot = self.get_thread_snapshot(project_id, node_id, thread_role, publish_repairs=False)
        if after_snapshot_version is not None and int(after_snapshot_version) > int(snapshot.get("snapshotVersion") or 0):
            from backend.errors.app_errors import ConversationStreamMismatch

            raise ConversationStreamMismatch()
        return snapshot
