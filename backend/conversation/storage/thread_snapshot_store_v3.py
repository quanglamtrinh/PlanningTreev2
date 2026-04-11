from __future__ import annotations

from pathlib import Path

from backend.config.app_config import AppPaths
from backend.conversation.domain.types_v3 import (
    ThreadRoleV3,
    ThreadSnapshotV3,
    default_thread_snapshot_v3,
    normalize_thread_snapshot_v3,
)
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore


class ThreadSnapshotStoreV3:
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

    def _conversation_dir(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "conversation_v3" / node_id

    def path(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> Path:
        return self._conversation_dir(project_id, node_id) / f"{thread_role}.json"

    def read_snapshot(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> ThreadSnapshotV3:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id, node_id, thread_role), default=None)
            return normalize_thread_snapshot_v3(
                payload,
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
            )

    def write_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3 | dict,
    ) -> ThreadSnapshotV3:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = normalize_thread_snapshot_v3(
                snapshot,
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
            )
            normalized["updatedAt"] = iso_now()
            target = self.path(project_id, node_id, thread_role)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return normalized

    def clear_snapshot(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> ThreadSnapshotV3:
        snapshot = default_thread_snapshot_v3(project_id, node_id, thread_role)
        return self.write_snapshot(project_id, node_id, thread_role, snapshot)

    def exists(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> bool:
        return self.path(project_id, node_id, thread_role).exists()
