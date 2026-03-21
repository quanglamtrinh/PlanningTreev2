from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_DEFAULT_STATE = {
    "thread_id": None,
    "active_job": None,
    "last_error": None,
}


class SplitStateStore:
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

    def path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "split_state.json"

    def read_state(self, project_id: str) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id), default=None)
            return self._normalize_state(payload)

    def write_state(self, project_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_state(state)
            atomic_write_json(self.path(project_id), normalized)
            return copy.deepcopy(normalized)

    def clear_state(self, project_id: str) -> dict[str, Any]:
        return self.write_state(project_id, _DEFAULT_STATE)

    def _normalize_state(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_STATE)

        thread_id = payload.get("thread_id")
        active_job = payload.get("active_job")
        last_error = payload.get("last_error")

        return {
            "thread_id": thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None,
            "active_job": self._normalize_active_job(active_job),
            "last_error": self._normalize_last_error(last_error),
        }

    def _normalize_active_job(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        job_id = payload.get("job_id")
        node_id = payload.get("node_id")
        mode = payload.get("mode")
        started_at = payload.get("started_at")
        if not all(isinstance(value, str) and value.strip() for value in (job_id, node_id, mode, started_at)):
            return None
        return {
            "job_id": job_id.strip(),
            "node_id": node_id.strip(),
            "mode": mode.strip(),
            "started_at": started_at.strip(),
        }

    def _normalize_last_error(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        started_at = payload.get("started_at")
        completed_at = payload.get("completed_at")
        if not all(isinstance(value, str) and value.strip() for value in (error, started_at, completed_at)):
            return None
        node_id = payload.get("node_id")
        mode = payload.get("mode")
        job_id = payload.get("job_id")
        return {
            "job_id": job_id.strip() if isinstance(job_id, str) and job_id.strip() else None,
            "node_id": node_id.strip() if isinstance(node_id, str) and node_id.strip() else None,
            "mode": mode.strip() if isinstance(mode, str) and mode.strip() else None,
            "started_at": started_at.strip(),
            "completed_at": completed_at.strip(),
            "error": error.strip(),
        }
