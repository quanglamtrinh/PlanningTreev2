from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from backend.errors.app_errors import InvalidRequest, NodeCreateNotAllowed, NodeNotFound
from backend.services import planningtree_workspace
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
            new_node_id = self._create_child_locked(
                snapshot=snapshot,
                node_by_id=node_by_id,
                parent=parent,
                parent_id=parent_id,
                title="New Node",
                description="",
            )
            snapshot["tree_state"]["active_node_id"] = new_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
            self._sync_snapshot_tree(snapshot)
        return self._public_snapshot(project_id, snapshot)

    def create_task(
        self,
        project_id: str,
        parent_id: str,
        description: str,
    ) -> Dict[str, Any]:
        cleaned_description = description.strip()
        if not cleaned_description:
            raise InvalidRequest("Task description is required.")

        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            parent = node_by_id.get(parent_id)
            if parent is None:
                raise NodeNotFound(parent_id)
            if not self._is_init_node(snapshot, parent):
                raise NodeCreateNotAllowed("Tasks can only be created from the init node.")
            new_node_id = self._create_child_locked(
                snapshot=snapshot,
                node_by_id=node_by_id,
                parent=parent,
                parent_id=parent_id,
                title="New Task",
                description=cleaned_description,
            )
            snapshot["tree_state"]["active_node_id"] = new_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
            self._sync_snapshot_tree(snapshot)
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
            title_changed = False
            if title is not None:
                cleaned_title = title.strip()
                if not cleaned_title:
                    raise InvalidRequest("Title cannot be empty.")
                if cleaned_title != node.get("title"):
                    node["title"] = cleaned_title
                    did_change = True
                    title_changed = True
            if description is not None and description != node.get("description"):
                node["description"] = description
                did_change = True

            if did_change:
                snapshot = self._persist_snapshot(project_id, snapshot)
                if title_changed:
                    self._sync_snapshot_tree(snapshot)
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

    def _is_init_node(self, snapshot: Dict[str, Any], node: Dict[str, Any]) -> bool:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            return False
        root_node_id = str(snapshot.get("tree_state", {}).get("root_node_id") or "").strip()
        if root_node_id and node_id == root_node_id:
            return True
        return str(node.get("node_kind") or "").strip() == "root"

    def _create_child_locked(
        self,
        *,
        snapshot: Dict[str, Any],
        node_by_id: Dict[str, Dict[str, Any]],
        parent: Dict[str, Any],
        parent_id: str,
        title: str,
        description: str,
    ) -> str:
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
            "title": title,
            "description": description,
            "status": child_status,
            "node_kind": "original",
            "depth": int(parent.get("depth", 0)) + 1,
            "display_order": display_order,
            "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
            "created_at": now,
        }
        snapshot["tree_state"]["node_index"][new_node_id] = child_node
        return new_node_id

    def _sync_snapshot_tree(self, snapshot: Dict[str, Any]) -> None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return
        project_path = str(project.get("project_path") or "").strip()
        if not project_path:
            return
        planningtree_workspace.sync_snapshot_tree(Path(project_path), snapshot)
