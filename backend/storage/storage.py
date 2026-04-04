from __future__ import annotations

from backend.config.app_config import AppPaths
from backend.conversation.storage.thread_registry_store import ThreadRegistryStore
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.storage.config_store import ConfigStore
from backend.storage.execution_state_store import ExecutionStateStore
from backend.storage.execution_run_store import ExecutionRunStore
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.project_store import ProjectStore
from backend.storage.chat_state_store import ChatStateStore
from backend.storage.review_state_store import ReviewStateStore
from backend.storage.review_cycle_store import ReviewCycleStore
from backend.storage.split_state_store import SplitStateStore
from backend.storage.workflow_state_store import WorkflowStateStore
from backend.storage.workspace_store import WorkspaceStore


class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._project_locks = ProjectLockRegistry()
        self.config_store = ConfigStore(paths)
        self.workspace_store = WorkspaceStore(paths)
        self._purge_legacy_projects_once()
        self.project_store = ProjectStore(paths, self.workspace_store, self._project_locks)
        self.split_state_store = SplitStateStore(paths, self.workspace_store, self._project_locks)
        self.chat_state_store = ChatStateStore(paths, self.workspace_store, self._project_locks)
        self.execution_state_store = ExecutionStateStore(paths, self.workspace_store, self._project_locks)
        self.review_state_store = ReviewStateStore(paths, self.workspace_store, self._project_locks)
        self.workflow_state_store = WorkflowStateStore(paths, self.workspace_store, self._project_locks)
        self.execution_run_store = ExecutionRunStore(paths, self.workspace_store, self._project_locks)
        self.review_cycle_store = ReviewCycleStore(paths, self.workspace_store, self._project_locks)
        self.thread_snapshot_store_v2 = ThreadSnapshotStoreV2(paths, self.workspace_store, self._project_locks)
        self.thread_registry_store = ThreadRegistryStore(paths, self.workspace_store, self._project_locks)

    def project_lock(self, project_id: str):
        return self._project_locks.for_project(project_id)

    def _purge_legacy_projects_once(self) -> None:
        if self.workspace_store.legacy_projects_purged():
            return
        if self.paths.projects_root.exists():
            import shutil

            shutil.rmtree(self.paths.projects_root, ignore_errors=True)
        self.workspace_store.mark_legacy_projects_purged()
