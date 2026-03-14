from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class TreeService:
    def node_index(self, snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        node_index = snapshot.get("tree_state", {}).get("node_index")
        if isinstance(node_index, dict):
            return node_index
        registry = snapshot.get("tree_state", {}).get("node_registry", [])
        if not isinstance(registry, list):
            return {}
        return {
            str(node["node_id"]): node
            for node in registry
            if isinstance(node, dict) and isinstance(node.get("node_id"), str)
        }

    def _is_superseded(self, node: Dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def active_child_ids(self, node: Dict[str, Any], node_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
        child_ids = node.get("child_ids", [])
        results: List[str] = []
        for child_id in child_ids:
            if not isinstance(child_id, str):
                continue
            child = node_by_id.get(child_id)
            if not child or self._is_superseded(child):
                continue
            results.append(child_id)
        return results

    def has_active_children(self, node: Dict[str, Any], node_by_id: Dict[str, Dict[str, Any]]) -> bool:
        return bool(self.active_child_ids(node, node_by_id))

    def has_locked_ancestor(
        self,
        node: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> bool:
        parent_id = node.get("parent_id")
        visited: Set[str] = set()
        while isinstance(parent_id, str) and parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = node_by_id.get(parent_id)
            if not parent:
                break
            if parent.get("status") == "locked":
                return True
            parent_id = parent.get("parent_id")
        return False

    def next_locked_sibling(
        self,
        node: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            return None
        parent = node_by_id.get(parent_id)
        if not parent:
            return None
        active_siblings = self.active_child_ids(parent, node_by_id)
        try:
            current_index = active_siblings.index(str(node["node_id"]))
        except ValueError:
            return None
        for sibling_id in active_siblings[current_index + 1 :]:
            sibling = node_by_id.get(sibling_id)
            if sibling and sibling.get("status") == "locked":
                return sibling
        return None

    def unlock_next_sibling(
        self,
        node: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        sibling = self.next_locked_sibling(node, node_by_id)
        if sibling is None:
            return None
        sibling["status"] = "ready"
        self.promote_first_active_descendant(sibling, node_by_id)
        return str(sibling["node_id"])

    def promote_first_active_descendant(
        self,
        node: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        current = node
        unlocked_node_id: Optional[str] = None
        visited: Set[str] = set()

        while True:
            current_id = str(current.get("node_id", ""))
            if not current_id or current_id in visited:
                return unlocked_node_id
            visited.add(current_id)

            active_children = self.active_child_ids(current, node_by_id)
            if not active_children:
                return unlocked_node_id

            next_child = node_by_id.get(active_children[0])
            if next_child is None:
                return unlocked_node_id

            if next_child.get("status") == "locked":
                next_child["status"] = "ready"
                unlocked_node_id = str(next_child["node_id"])

            current = next_child

    def first_actionable_leaf(
        self,
        snapshot: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        root_id = snapshot.get("tree_state", {}).get("root_node_id")
        if not isinstance(root_id, str) or not root_id:
            return None
        root = node_by_id.get(root_id)
        if root is None or self._is_superseded(root):
            return None
        return self._first_actionable_leaf_from(root, node_by_id)

    def _first_actionable_leaf_from(
        self,
        node: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        active_children = self.active_child_ids(node, node_by_id)
        if not active_children:
            if node.get("status") in {"ready", "in_progress"}:
                return str(node.get("node_id"))
            return None

        for child_id in active_children:
            child = node_by_id.get(child_id)
            if child is None or self._is_superseded(child):
                continue
            leaf_id = self._first_actionable_leaf_from(child, node_by_id)
            if leaf_id:
                return leaf_id
        return None
