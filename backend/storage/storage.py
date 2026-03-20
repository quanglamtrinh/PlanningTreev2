from __future__ import annotations

from backend.config.app_config import AppPaths
from backend.storage.chat_store import ChatStore
from backend.storage.config_store import ConfigStore
from backend.storage.node_store import NodeStore
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.project_store import ProjectStore
from backend.storage.thread_store import ThreadStore


class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._project_locks = ProjectLockRegistry()
        self.node_store = NodeStore(paths)
        self.config_store = ConfigStore(paths)
        self.project_store = ProjectStore(paths, self._project_locks, self.node_store)
        self.chat_store = ChatStore(paths, self._project_locks)
        self.thread_store = ThreadStore(paths, self._project_locks)

    def project_lock(self, project_id: str):
        return self._project_locks.for_project(project_id)
