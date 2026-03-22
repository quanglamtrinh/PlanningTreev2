from __future__ import annotations

import copy
from typing import Any


class SnapshotViewService:
    """Converts internal snapshots into public API payloads."""

    def to_public_snapshot(
        self,
        project_id: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        del project_id
        public_snapshot = copy.deepcopy(snapshot)
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
            registry.append(node)
        tree_state["node_registry"] = registry
        return public_snapshot
