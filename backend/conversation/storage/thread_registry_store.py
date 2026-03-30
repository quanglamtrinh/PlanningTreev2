from __future__ import annotations

from pathlib import Path

from backend.config.app_config import AppPaths
from backend.conversation.domain.types import ThreadRegistryEntry, ThreadRole, default_thread_registry_entry, normalize_thread_registry_entry
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore


class ThreadRegistryStore:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _registry_dir(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "thread_registry" / node_id

    def path(self, project_id: str, node_id: str, thread_role: ThreadRole) -> Path:
        return self._registry_dir(project_id, node_id) / f"{thread_role}.json"

    def read_entry(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id, node_id, thread_role), default=None)
            return normalize_thread_registry_entry(
                payload,
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
            )

    def write_entry(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        entry: ThreadRegistryEntry | dict,
    ) -> ThreadRegistryEntry:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = normalize_thread_registry_entry(
                entry,
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
            )
            normalized["updatedAt"] = iso_now()
            target = self.path(project_id, node_id, thread_role)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return normalized

    def clear_entry(self, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
        entry = default_thread_registry_entry(project_id, node_id, thread_role)
        return self.write_entry(project_id, node_id, thread_role, entry)

    def exists(self, project_id: str, node_id: str, thread_role: ThreadRole) -> bool:
        return self.path(project_id, node_id, thread_role).exists()
