from __future__ import annotations

from typing import Any, Dict

from backend.config.app_config import AppPaths
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry


class ChatStore:
    def __init__(self, paths: AppPaths, lock_registry: ProjectLockRegistry) -> None:
        self._paths = paths
        self._lock_registry = lock_registry

    def _chat_state_path(self, project_id: str):
        normalized = normalize_project_id(project_id)
        return self._paths.projects_root / normalized / "chat_state.json"

    def project_lock(self, project_id: str):
        return self._lock_registry.for_project(project_id)

    def read_chat_state(self, project_id: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            return load_json(self._chat_state_path(project_id), default={}) or {}

    def write_chat_state(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.project_lock(project_id):
            atomic_write_json(self._chat_state_path(project_id), payload)
            return payload
