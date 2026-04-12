from __future__ import annotations

from typing import Any

from backend.conversation.domain.types import ThreadRegistryEntry, ThreadRole, copy_registry_entry
from backend.conversation.storage.thread_registry_store import ThreadRegistryStore
from backend.storage.file_utils import iso_now


class ThreadRegistryService:
    def __init__(self, store: ThreadRegistryStore) -> None:
        self._store = store

    def read_entry(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
        return self._store.read_entry(project_id, node_id, thread_role)

    def seed_from_legacy_session(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        session: dict[str, Any],
    ) -> tuple[ThreadRegistryEntry, bool]:
        entry = self._store.read_entry(project_id, node_id, thread_role)
        updated = copy_registry_entry(entry)
        changed = False

        def maybe_set(field: str, value: Any) -> None:
            nonlocal changed
            if value in (None, ""):
                return
            if updated.get(field) != value:
                updated[field] = value
                changed = True

        maybe_set("threadId", session.get("thread_id"))
        maybe_set("forkedFromThreadId", session.get("forked_from_thread_id"))
        maybe_set("forkedFromNodeId", session.get("forked_from_node_id"))
        maybe_set("forkedFromRole", session.get("forked_from_role"))
        maybe_set("forkReason", session.get("fork_reason"))
        maybe_set("lineageRootThreadId", session.get("lineage_root_thread_id"))

        if changed:
            updated["updatedAt"] = iso_now()
            updated = self._store.write_entry(project_id, node_id, thread_role, updated)
        return updated, changed

    _UNSET = object()

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return None

    def update_entry(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        *,
        thread_id: str | None | object = _UNSET,
        forked_from_thread_id: str | None | object = _UNSET,
        forked_from_node_id: str | None | object = _UNSET,
        forked_from_role: ThreadRole | None | object = _UNSET,
        fork_reason: str | None | object = _UNSET,
        lineage_root_thread_id: str | None | object = _UNSET,
        event_cursor_thread_id: str | None | object = _UNSET,
        last_event_sequence: int | object = _UNSET,
        last_event_id: str | None | object = _UNSET,
    ) -> ThreadRegistryEntry:
        entry = self._store.read_entry(project_id, node_id, thread_role)
        if thread_id is not self._UNSET:
            entry["threadId"] = thread_id
        if forked_from_thread_id is not self._UNSET:
            entry["forkedFromThreadId"] = forked_from_thread_id
        if forked_from_node_id is not self._UNSET:
            entry["forkedFromNodeId"] = forked_from_node_id
        if forked_from_role is not self._UNSET:
            entry["forkedFromRole"] = forked_from_role
        if fork_reason is not self._UNSET:
            entry["forkReason"] = fork_reason
        if lineage_root_thread_id is not self._UNSET:
            entry["lineageRootThreadId"] = lineage_root_thread_id
        if event_cursor_thread_id is not self._UNSET:
            entry["eventCursorThreadId"] = event_cursor_thread_id
        if last_event_sequence is not self._UNSET:
            entry["lastEventSequence"] = max(0, int(last_event_sequence))
        if last_event_id is not self._UNSET:
            entry["lastEventId"] = last_event_id
        entry["updatedAt"] = iso_now()
        return self._store.write_entry(project_id, node_id, thread_role, entry)

    def issue_next_event_id(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        *,
        thread_id: str | None,
    ) -> str:
        entry = self._store.read_entry(project_id, node_id, thread_role)
        normalized_thread_id = (
            self._normalize_optional_string(thread_id)
            or self._normalize_optional_string(entry.get("threadId"))
            or self._normalize_optional_string(entry.get("eventCursorThreadId"))
            or f"unbound::{thread_role}"
        )

        cursor_thread_id = self._normalize_optional_string(entry.get("eventCursorThreadId"))
        next_sequence = int(entry.get("lastEventSequence") or 0)
        if cursor_thread_id != normalized_thread_id:
            next_sequence = 0

        next_sequence += 1
        entry["eventCursorThreadId"] = normalized_thread_id
        entry["lastEventSequence"] = next_sequence
        entry["lastEventId"] = str(next_sequence)
        entry["updatedAt"] = iso_now()
        self._store.write_entry(project_id, node_id, thread_role, entry)
        return str(next_sequence)

    def clear_entry(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
        return self._store.clear_entry(project_id, node_id, thread_role)
