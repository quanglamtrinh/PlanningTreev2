from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from backend.errors.app_errors import FinishTaskNotAllowed, NodeNotFound
from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)


class FinishTaskService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        node_detail_service: NodeDetailService,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._node_detail_service = node_detail_service

    def finish_task(self, project_id: str, node_id: str) -> dict[str, Any]:
        """Initiate execution for a node. Validates preconditions, writes
        execution_state, updates node status, and returns updated detail state.

        Preconditions (per execution-state-model.md):
        1. Spec confirmed (spec.meta.json has confirmed_at)
        2. Node is leaf (child_ids empty)
        3. Node status is ready or in_progress
        4. No active execution (execution_state does not exist)
        """
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            # Precondition 1: spec confirmed
            node_dir = self._resolve_node_dir(snapshot, node_id)
            from backend.services.node_detail_service import _load_spec_meta_from_node_dir
            spec_meta = _load_spec_meta_from_node_dir(node_dir)
            if not spec_meta.get("confirmed_at"):
                raise FinishTaskNotAllowed("Spec must be confirmed before Finish Task.")

            # Precondition 2: leaf node
            child_ids = node.get("child_ids") or []
            if len(child_ids) > 0:
                raise FinishTaskNotAllowed("Finish Task is only available for leaf nodes (no children).")

            # Precondition 3: node status
            node_status = node.get("status", "")
            if node_status not in ("ready", "in_progress"):
                raise FinishTaskNotAllowed(
                    f"Node status must be 'ready' or 'in_progress', got '{node_status}'."
                )

            # Precondition 4: no existing execution
            if self._storage.execution_state_store.exists(project_id, node_id):
                raise FinishTaskNotAllowed("Execution has already been started for this node.")

            # ── All preconditions met. Execute effects atomically. ──

            now = iso_now()
            initial_sha = self._compute_initial_sha(project_id, node_id, snapshot)

            # Write execution_state
            exec_state = {
                "status": "executing",
                "initial_sha": initial_sha,
                "head_sha": None,
                "started_at": now,
                "completed_at": None,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            # Update node status to in_progress (stays coarse)
            if node.get("status") != "in_progress":
                node["status"] = "in_progress"
                snapshot["updated_at"] = now
                self._storage.project_store.save_snapshot(project_id, snapshot)

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def complete_execution(
        self, project_id: str, node_id: str, head_sha: str | None = None
    ) -> dict[str, Any]:
        """Called when Codex execution finishes. Sets status to completed."""
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise FinishTaskNotAllowed("No execution state exists for this node.")
            if exec_state.get("status") != "executing":
                raise FinishTaskNotAllowed(
                    f"Cannot complete execution: status is '{exec_state.get('status')}', expected 'executing'."
                )

            exec_state["status"] = "completed"
            exec_state["head_sha"] = head_sha
            exec_state["completed_at"] = iso_now()
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def _compute_initial_sha(
        self, project_id: str, node_id: str, snapshot: dict[str, Any]
    ) -> str:
        """Compute initial_sha per execution-state-model.md source selection.

        If node belongs to a checkpointed sibling chain: use latest checkpoint SHA.
        Otherwise: compute workspace SHA at Finish Task time.
        """
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        node = node_index.get(node_id, {})
        parent_id = node.get("parent_id")

        if parent_id:
            parent = node_index.get(parent_id, {})
            review_node_id = parent.get("review_node_id")
            if review_node_id:
                review_state = self._storage.review_state_store.read_state(
                    project_id, review_node_id
                )
                if review_state:
                    checkpoints = review_state.get("checkpoints", [])
                    if checkpoints:
                        return checkpoints[-1]["sha"]

        # Fallback: compute workspace SHA
        return self._compute_workspace_sha(snapshot)

    def _compute_workspace_sha(self, snapshot: dict[str, Any]) -> str:
        """Placeholder workspace SHA — SHA-256 of project path + timestamp.

        Real implementation will hash the workspace directory tree or use git SHA.
        """
        project = snapshot.get("project", {})
        project_path = project.get("project_path", "")
        content = f"{project_path}:{iso_now()}"
        digest = hashlib.sha256(content.encode()).hexdigest()
        return f"sha256:{digest}"

    def _resolve_node_dir(self, snapshot: dict[str, Any], node_id: str) -> Path:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(raw_path)
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
        if node_dir is None:
            raise NodeNotFound(node_id)
        return node_dir
