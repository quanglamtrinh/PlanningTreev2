from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from backend.errors.app_errors import InvalidRequest, NodeCreateNotAllowed, NodeNotFound
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage


class NodeService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        snapshot_view_service: SnapshotViewService | None = None,
    ) -> None:
        self.storage = storage
        self.tree_service = tree_service
        self._snapshot_view_service = snapshot_view_service

    def set_active_node(self, project_id: str, active_node_id: Optional[str]) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            if active_node_id is not None and active_node_id not in node_by_id:
                raise NodeNotFound(active_node_id)
            if snapshot["tree_state"].get("active_node_id") == active_node_id:
                return self._public_snapshot(project_id, snapshot)
            snapshot["tree_state"]["active_node_id"] = active_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def create_child(self, project_id: str, parent_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            parent = node_by_id.get(parent_id)
            if parent is None:
                raise NodeNotFound(parent_id)
            if self._is_superseded(parent):
                raise NodeCreateNotAllowed("Cannot create a child under a superseded node.")
            if parent.get("status") == "done":
                raise NodeCreateNotAllowed("Cannot create a child under a done node.")

            now = iso_now()
            active_children = self.tree_service.active_child_ids(parent, node_by_id)
            display_order = len(active_children)
            new_node_id = uuid4().hex

            child_status = "ready"
            if active_children:
                child_status = "locked"
            elif parent.get("status") == "locked" or self.tree_service.has_locked_ancestor(parent, node_by_id):
                child_status = "locked"

            if not active_children and parent.get("status") in {"ready", "in_progress"}:
                parent["status"] = "draft"

            parent.setdefault("child_ids", []).append(new_node_id)
            parent_hnum = str(parent.get("hierarchical_number") or "1")
            child_node = {
                "node_id": new_node_id,
                "parent_id": parent_id,
                "child_ids": [],
                "title": "New Node",
                "description": "",
                "status": child_status,
                "node_kind": "original",
                "depth": int(parent.get("depth", 0)) + 1,
                "display_order": display_order,
                "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
                "created_at": now,
            }
            snapshot["tree_state"]["node_index"][new_node_id] = child_node
            snapshot["tree_state"]["active_node_id"] = new_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def update_node(
        self,
        project_id: str,
        node_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if title is None and description is None:
            raise InvalidRequest("Provide at least one field to update.")

        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            did_change = False
            if title is not None:
                cleaned_title = title.strip()
                if not cleaned_title:
                    raise InvalidRequest("Title cannot be empty.")
                if cleaned_title != node.get("title"):
                    node["title"] = cleaned_title
                    did_change = True
            if description is not None and description != node.get("description"):
                node["description"] = description
                did_change = True

            if did_change:
                snapshot = self._persist_snapshot(project_id, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def _persist_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        snapshot["updated_at"] = iso_now()
        self.storage.project_store.save_snapshot(project_id, snapshot)
        meta = self.storage.project_store.touch_meta(project_id, snapshot["updated_at"])
        snapshot["project"] = meta
        return snapshot

    def _public_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if self._snapshot_view_service is None:
            return snapshot
        return self._snapshot_view_service.to_public_snapshot(project_id, snapshot)

    def _is_superseded(self, node: Dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))
