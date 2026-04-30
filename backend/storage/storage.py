from __future__ import annotations

from backend.config.app_config import AppPaths
from backend.storage.config_store import ConfigStore
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.project_store import ProjectStore
from backend.storage.workflow_domain_store import WorkflowDomainStore
from backend.storage.workspace_store import WorkspaceStore


class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._project_locks = ProjectLockRegistry()
        self.config_store = ConfigStore(paths)
        self.workspace_store = WorkspaceStore(paths)
        self.project_store = ProjectStore(paths, self.workspace_store, self._project_locks)
        self.workflow_domain_store = WorkflowDomainStore(paths, self.workspace_store, self._project_locks)

    def project_lock(self, project_id: str):
        return self._project_locks.for_project(project_id)
