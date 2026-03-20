from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Dict, List

from backend.config.app_config import AppPaths
from backend.errors.app_errors import LegacyProjectUnsupported, ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry

CURRENT_SCHEMA_VERSION = 6
_ALLOWED_NODE_FIELDS = {
    "node_id",
    "parent_id",
    "child_ids",
    "title",
    "description",
    "status",
    "node_kind",
    "depth",
    "display_order",
    "hierarchical_number",
    "created_at",
}
_ALLOWED_NODE_KINDS = {"root", "original", "superseded"}
_ALLOWED_NODE_STATUSES = {"locked", "draft", "ready", "in_progress", "done"}


class ProjectStore:
    def __init__(
        self,
        paths: AppPaths,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._lock_registry = lock_registry

    def project_dir(self, project_id: str) -> Path:
        return self._paths.projects_root / normalize_project_id(project_id)

    def project_lock(self, project_id: str):
        return self._lock_registry.for_project(project_id)

    def meta_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "meta.json"

    def state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "state.json"

    def tree_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "tree.json"

    def create_project_files(self, meta: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
        project_id = str(meta["id"])
        with self.project_lock(project_id):
            project_dir = ensure_dir(self.project_dir(project_id))
            atomic_write_json(project_dir / "meta.json", meta)
            atomic_write_json(project_dir / "tree.json", self._normalize_snapshot_for_persistence(snapshot))

    def save_tree(self, project_id: str, tree: Dict[str, Any]) -> None:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            atomic_write_json(self.tree_path(project_id), self._normalize_snapshot_for_persistence(tree))

    def save_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> None:
        self.save_tree(project_id, snapshot)

    def load_tree(self, project_id: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            if self._has_legacy_artifacts(project_dir):
                raise LegacyProjectUnsupported(project_id)
            tree = load_json(self.tree_path(project_id))
            if not isinstance(tree, dict):
                raise ProjectNotFound(project_id)
            if self._schema_version(tree) != CURRENT_SCHEMA_VERSION:
                raise LegacyProjectUnsupported(project_id)
            normalized = self._normalize_snapshot_for_persistence(tree)
            self._validate_snapshot(project_id, normalized)
            return normalized

    def load_snapshot(self, project_id: str) -> Dict[str, Any]:
        return self.load_tree(project_id)

    def load_meta(self, project_id: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            meta = load_json(self.meta_path(project_id))
            if meta is None:
                raise ProjectNotFound(project_id)
            return meta

    def save_meta(self, project_id: str, meta: Dict[str, Any]) -> None:
        with self.project_lock(project_id):
            if not self.project_dir(project_id).exists():
                raise ProjectNotFound(project_id)
            atomic_write_json(self.meta_path(project_id), meta)

    def touch_meta(self, project_id: str, updated_at: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            meta = self.load_meta(project_id)
            meta["updated_at"] = updated_at
            self.save_meta(project_id, meta)
            return meta

    def delete_project(self, project_id: str) -> None:
        project_dir = self.project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)

    def list_projects(self) -> List[Dict[str, Any]]:
        ensure_dir(self._paths.projects_root)
        projects: List[Dict[str, Any]] = []
        for project_dir in self._paths.projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            meta = load_json(project_dir / "meta.json")
            if isinstance(meta, dict):
                projects.append(meta)
        projects.sort(
            key=lambda item: (str(item.get("updated_at", "")), str(item.get("name", ""))),
            reverse=True,
        )
        return projects

    def list_project_ids(self) -> List[str]:
        ensure_dir(self._paths.projects_root)
        project_ids: List[str] = []
        for project_dir in self._paths.projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            try:
                project_ids.append(normalize_project_id(project_dir.name))
            except Exception:
                continue
        return sorted(project_ids)

    def _schema_version(self, snapshot: Dict[str, Any]) -> int:
        try:
            return int(snapshot.get("schema_version", 0))
        except (TypeError, ValueError):
            return 0

    def _has_legacy_artifacts(self, project_dir: Path) -> bool:
        return any(
            (
                (project_dir / "nodes").exists(),
                (project_dir / "chat_state.json").exists(),
                (project_dir / "thread_state.json").exists(),
                (project_dir / "state.json").exists(),
            )
        )

    def _normalize_snapshot_for_persistence(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(snapshot)
        normalized["schema_version"] = CURRENT_SCHEMA_VERSION
        tree_state = normalized.get("tree_state")
        if not isinstance(tree_state, dict):
            tree_state = {}
            normalized["tree_state"] = tree_state
        node_index = tree_state.get("node_index")
        if not isinstance(node_index, dict):
            node_index = {}
            tree_state["node_index"] = node_index
        for node_id, raw_node in list(node_index.items()):
            if not isinstance(raw_node, dict):
                node_index.pop(node_id, None)
                continue
            node_index[node_id] = self._normalize_node(raw_node)
        tree_state.pop("node_registry", None)
        return normalized

    def _normalize_node(self, raw_node: Dict[str, Any]) -> Dict[str, Any]:
        node = {key: value for key, value in raw_node.items() if key in _ALLOWED_NODE_FIELDS}
        child_ids = node.get("child_ids")
        if not isinstance(child_ids, list):
            node["child_ids"] = []
        else:
            node["child_ids"] = [child_id for child_id in child_ids if isinstance(child_id, str) and child_id]
        node["title"] = str(node.get("title") or "").strip()
        node["description"] = str(node.get("description") or "")
        status = str(node.get("status") or "draft")
        node["status"] = status if status in _ALLOWED_NODE_STATUSES else "draft"
        node_kind = str(node.get("node_kind") or "original")
        node["node_kind"] = node_kind if node_kind in _ALLOWED_NODE_KINDS else "original"
        node["depth"] = int(node.get("depth", 0) or 0)
        node["display_order"] = int(node.get("display_order", 0) or 0)
        node["hierarchical_number"] = str(node.get("hierarchical_number") or "")
        node["created_at"] = str(node.get("created_at") or "")
        parent_id = node.get("parent_id")
        node["parent_id"] = parent_id if isinstance(parent_id, str) and parent_id else None
        node_id = str(node.get("node_id") or "").strip()
        if node_id:
            node["node_id"] = node_id
        return node

    def _validate_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> None:
        tree_state = snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            raise LegacyProjectUnsupported(project_id)
        root_node_id = str(tree_state.get("root_node_id") or "").strip()
        node_index = tree_state.get("node_index")
        if not root_node_id or not isinstance(node_index, dict) or root_node_id not in node_index:
            raise LegacyProjectUnsupported(project_id)
