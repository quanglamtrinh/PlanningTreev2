from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_STATUSES = {"idle", "executing", "completed", "review_pending", "review_accepted"}

_DEFAULT_STATE: dict[str, Any] = {
    "status": "idle",
    "initial_sha": None,
    "head_sha": None,
    "started_at": None,
    "completed_at": None,
}


class ExecutionStateStore:
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

    def _execution_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "execution"

    def path(self, project_id: str, node_id: str) -> Path:
        return self._execution_dir(project_id) / f"{node_id}.json"

    def exists(self, project_id: str, node_id: str) -> bool:
        """Check if execution state file exists (canonical signal for execution phase)."""
        return self.path(project_id, node_id).exists()

    def read_state(self, project_id: str, node_id: str) -> dict[str, Any] | None:
        """Read execution state. Returns None if file does not exist (no execution)."""
        with self._lock_registry.for_project(project_id):
            p = self.path(project_id, node_id)
            if not p.exists():
                return None
            payload = load_json(p, default=None)
            return self._normalize_state(payload)

    def write_state(self, project_id: str, node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        """Write execution state. Creates the file if it doesn't exist."""
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_state(state)
            target = self.path(project_id, node_id)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return copy.deepcopy(normalized)

    def _normalize_state(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_STATE)

        status = payload.get("status")
        initial_sha = payload.get("initial_sha")
        head_sha = payload.get("head_sha")
        started_at = payload.get("started_at")
        completed_at = payload.get("completed_at")

        return {
            "status": status if isinstance(status, str) and status in _VALID_STATUSES else "idle",
            "initial_sha": initial_sha.strip() if isinstance(initial_sha, str) and initial_sha.strip() else None,
            "head_sha": head_sha.strip() if isinstance(head_sha, str) and head_sha.strip() else None,
            "started_at": started_at.strip() if isinstance(started_at, str) and started_at.strip() else None,
            "completed_at": completed_at.strip() if isinstance(completed_at, str) and completed_at.strip() else None,
        }
