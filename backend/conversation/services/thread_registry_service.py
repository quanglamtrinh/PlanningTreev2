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
        entry["updatedAt"] = iso_now()
        return self._store.write_entry(project_id, node_id, thread_role, entry)

    def clear_entry(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
        return self._store.clear_entry(project_id, node_id, thread_role)
