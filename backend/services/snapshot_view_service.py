from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.services import planningtree_workspace
from backend.services.node_detail_service import derive_workflow_summary_from_node_dir
from backend.services.execution_gating import derive_execution_workflow_fields
from backend.services.review_sibling_manifest import (
    derive_review_sibling_manifest,
    to_public_pending_siblings,
)
from backend.storage.storage import Storage


class SnapshotViewService:
    """Converts internal snapshots into public API payloads."""

    def __init__(self, storage: Storage | None = None) -> None:
        self._storage = storage

    def to_public_snapshot(
        self,
        project_id: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        public_snapshot = copy.deepcopy(snapshot)
        project = public_snapshot.get("project", {})
        project_path = None
        if isinstance(project, dict):
            raw_project_path = str(project.get("project_path") or "").strip()
            if raw_project_path:
                project_path = Path(raw_project_path)
        tree_state = public_snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return public_snapshot
        node_index = tree_state.pop("node_index", {})
        if not isinstance(node_index, dict):
            tree_state["node_registry"] = []
            return public_snapshot
        registry = []
        root_node_id = str(tree_state.get("root_node_id") or "")
        for raw_node in node_index.values():
            if not isinstance(raw_node, dict):
                continue
            node = dict(raw_node)
            node_id = str(node.get("node_id") or "")
            node_kind = str(node.get("node_kind") or "").strip()
            if node_id and node_id == root_node_id:
                node_kind = "root"
            elif node_kind not in {"root", "original", "superseded", "review"}:
                node_kind = "original"
            node["node_kind"] = node_kind
            node["is_superseded"] = node_kind == "superseded"
            if node_kind == "review":
                node["workflow"] = None
                node["review_summary"] = self._review_summary(project_id, snapshot, node)
            else:
                node["workflow"] = self._workflow_summary(
                    project_id=project_id,
                    project_path=project_path,
                    snapshot=public_snapshot,
                    node=node,
                    node_id=node_id,
                )
            registry.append(node)
        tree_state["node_registry"] = registry
        return public_snapshot

    def _workflow_summary(
        self,
        *,
        project_id: str,
        project_path: Path | None,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_id: str,
    ) -> dict[str, Any]:
        if project_path is None or not node_id:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
                "execution_started": False,
                "execution_completed": False,
                "shaping_frozen": False,
                "can_finish_task": False,
                "execution_status": None,
            }
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
        if node_dir is None:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
                "execution_started": False,
                "execution_completed": False,
                "shaping_frozen": False,
                "can_finish_task": False,
                "execution_status": None,
            }
        workflow = derive_workflow_summary_from_node_dir(node_dir)
        if self._storage is None:
            return workflow

        review_state = None
        review_node_id = str(node.get("review_node_id") or "").strip()
        if review_node_id:
            review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        workflow.update(
            derive_execution_workflow_fields(
                self._storage,
                project_id,
                node_id,
                workflow=workflow,
                node=node,
                exec_state=exec_state,
                review_state=review_state,
            )
        )
        for field in ("audit_writable", "package_audit_ready", "review_status"):
            workflow.pop(field, None)
        return workflow

    def _review_summary(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        review_node: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._storage is None:
            return None
        review_node_id = str(review_node.get("node_id") or "").strip()
        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if not isinstance(review_state, dict):
            return None
        checkpoints = review_state.get("checkpoints", [])
        rollup = review_state.get("rollup", {})
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        parent_id = str(review_node.get("parent_id") or "").strip()
        parent_node = node_index.get(parent_id) if isinstance(node_index, dict) and parent_id else None
        sibling_manifest = (
            derive_review_sibling_manifest(snapshot, parent_node, review_node, review_state)
            if isinstance(parent_node, dict)
            else []
        )
        pending_siblings = to_public_pending_siblings(review_state)
        return {
            "checkpoint_count": len(checkpoints) if isinstance(checkpoints, list) else 0,
            "rollup_status": str(rollup.get("status")) if isinstance(rollup, dict) and rollup.get("status") else None,
            "pending_sibling_count": sum(1 for sibling in sibling_manifest if sibling.get("status") == "pending"),
            "pending_siblings": pending_siblings,
            "sibling_manifest": sibling_manifest,
        }
