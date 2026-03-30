from __future__ import annotations

from typing import Any

from backend.conversation.domain.types import ConversationItem, ThreadRole, copy_snapshot, next_snapshot_version
from backend.conversation.projector.thread_event_projector import upsert_item
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage


class ConversationSystemMessageWriter:
    def __init__(self, storage: Storage, runtime_service: Any | None = None) -> None:
        self._storage = storage
        self._runtime_service = runtime_service

    def set_runtime_service(self, runtime_service: Any) -> None:
        self._runtime_service = runtime_service

    def upsert_system_message(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        item_id: str,
        turn_id: str | None,
        text: str,
        tone: str = "neutral",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._runtime_service is not None:
            return self._runtime_service.upsert_system_message(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                item_id=item_id,
                turn_id=turn_id,
                text=text,
                tone=tone,
                metadata=metadata,
            )
        return self._fallback_upsert_system_message(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            item_id=item_id,
            turn_id=turn_id,
            text=text,
            tone=tone,
            metadata=metadata,
        )

    def _fallback_upsert_system_message(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        item_id: str,
        turn_id: str | None,
        text: str,
        tone: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = iso_now()
        with self._storage.project_lock(project_id):
            snapshot = copy_snapshot(
                self._storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, thread_role)
            )
            registry_entry = self._storage.thread_registry_store.read_entry(project_id, node_id, thread_role)
            thread_id = str(snapshot.get("threadId") or registry_entry.get("threadId") or "").strip()
            if not thread_id:
                raise ValueError(
                    f"Cannot upsert V2 system message for {project_id}/{node_id}/{thread_role}: missing threadId."
                )
            item: ConversationItem = {
                "id": item_id,
                "kind": "message",
                "threadId": thread_id,
                "turnId": turn_id,
                "sequence": self._next_sequence(snapshot),
                "createdAt": now,
                "updatedAt": now,
                "status": "completed",
                "source": "backend",
                "tone": tone,  # type: ignore[typeddict-item]
                "metadata": dict(metadata or {}),
                "role": "system",
                "text": str(text or ""),
                "format": "markdown",
            }
            updated, _ = upsert_item(snapshot, item)
            updated["snapshotVersion"] = next_snapshot_version(updated)
            updated["updatedAt"] = now
            return self._storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, thread_role, updated)

    @staticmethod
    def _next_sequence(snapshot: dict[str, Any]) -> int:
        return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1
