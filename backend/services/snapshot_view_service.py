from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.services import planningtree_workspace
from backend.services.node_detail_service import derive_workflow_summary_from_node_dir


class SnapshotViewService:
    """Converts internal snapshots into public API payloads."""

    def to_public_snapshot(
        self,
        project_id: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        del project_id
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
            elif node_kind not in {"root", "original", "superseded"}:
                node_kind = "original"
            node["node_kind"] = node_kind
            node["is_superseded"] = node_kind == "superseded"
            node["workflow"] = self._workflow_summary(
                project_path=project_path,
                snapshot=public_snapshot,
                node_id=node_id,
            )
            registry.append(node)
        tree_state["node_registry"] = registry
        return public_snapshot

    def _workflow_summary(
        self,
        *,
        project_path: Path | None,
        snapshot: dict[str, Any],
        node_id: str,
    ) -> dict[str, Any]:
        if project_path is None or not node_id:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
            }
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
        if node_dir is None:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
            }
        return derive_workflow_summary_from_node_dir(node_dir)
