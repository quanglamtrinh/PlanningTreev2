from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound, UnsupportedProjectLayout
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

CURRENT_SCHEMA_VERSION = 6
PLANNINGTREE_DIR = ".planningtree"
_ALLOWED_META_FIELDS = {
    "id",
    "name",
    "root_goal",
    "created_at",
    "updated_at",
}
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
    "review_node_id",
}
_ALLOWED_NODE_KINDS = {"root", "original", "superseded", "review"}
_ALLOWED_NODE_STATUSES = {"locked", "draft", "ready", "in_progress", "done"}


class ProjectStore:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def project_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return self.project_dir_for_folder(folder_path)

    def project_dir_for_folder(self, folder_path: str | Path) -> Path:
        return Path(folder_path).expanduser().resolve() / PLANNINGTREE_DIR

    def project_lock(self, project_id: str):
        return self._lock_registry.for_project(project_id)

    def meta_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "meta.json"

    def meta_path_for_folder(self, folder_path: str | Path) -> Path:
        return self.project_dir_for_folder(folder_path) / "meta.json"

    def state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "state.json"

    def tree_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "tree.json"

    def tree_path_for_folder(self, folder_path: str | Path) -> Path:
        return self.project_dir_for_folder(folder_path) / "tree.json"

    def create_project_files(self, folder_path: str, meta: dict[str, Any], snapshot: dict[str, Any]) -> None:
        project_id = str(meta["id"])
        with self.project_lock(project_id):
            project_dir = ensure_dir(self.project_dir_for_folder(folder_path))
            atomic_write_json(project_dir / "meta.json", self._sanitize_meta(meta))
            atomic_write_json(project_dir / "tree.json", self._normalize_snapshot_for_persistence(snapshot))

    def save_tree(self, project_id: str, tree: dict[str, Any]) -> None:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            atomic_write_json(self.tree_path(project_id), self._normalize_snapshot_for_persistence(tree))

    def save_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> None:
        self.save_tree(project_id, snapshot)

    def load_tree(self, project_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            return self._load_snapshot_from_dir(project_id, project_dir)

    def load_snapshot(self, project_id: str) -> dict[str, Any]:
        return self.load_tree(project_id)

    def load_snapshot_from_folder(self, folder_path: str) -> dict[str, Any]:
        project_dir = self.project_dir_for_folder(folder_path)
        meta = self.load_meta_from_folder(folder_path)
        project_id = str(meta["id"])
        with self.project_lock(project_id):
            return self._load_snapshot_from_dir(project_id, project_dir)

    def load_meta(self, project_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            meta = load_json(project_dir / "meta.json")
            if not isinstance(meta, dict):
                raise ProjectNotFound(project_id)
            return self._runtime_meta(meta, self._workspace_store.get_folder_path(project_id))

    def load_meta_from_folder(self, folder_path: str) -> dict[str, Any]:
        project_dir = self.project_dir_for_folder(folder_path)
        meta = load_json(project_dir / "meta.json")
        if not isinstance(meta, dict):
            raise UnsupportedProjectLayout("unattached-folder")
        sanitized = self._sanitize_meta(meta)
        project_id = sanitized.get("id")
        if not isinstance(project_id, str) or not project_id:
            raise UnsupportedProjectLayout("unattached-folder")
        return self._runtime_meta(sanitized, str(Path(folder_path).expanduser().resolve()))

    def save_meta(self, project_id: str, meta: dict[str, Any]) -> None:
        with self.project_lock(project_id):
            project_dir = self.project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            atomic_write_json(self.meta_path(project_id), self._sanitize_meta(meta))

    def touch_meta(self, project_id: str, updated_at: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            meta = self.load_meta(project_id)
            meta["updated_at"] = updated_at
            self.save_meta(project_id, meta)
            return self.load_meta(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        stale_project_ids: list[str] = []
        for entry in self._workspace_store.list_entries():
            project_id = entry["project_id"]
            folder_path = entry["folder_path"]
            project_dir = self.project_dir_for_folder(folder_path)
            if not Path(folder_path).exists() or not project_dir.exists():
                stale_project_ids.append(project_id)
                continue
            meta = load_json(project_dir / "meta.json")
            if not isinstance(meta, dict):
                stale_project_ids.append(project_id)
                continue
            try:
                runtime_meta = self._runtime_meta(meta, folder_path)
            except Exception:
                stale_project_ids.append(project_id)
                continue
            if runtime_meta["id"] != project_id:
                stale_project_ids.append(project_id)
                continue
            projects.append(runtime_meta)
        if stale_project_ids:
            self._workspace_store.prune_projects(stale_project_ids)
        projects.sort(
            key=lambda item: (str(item.get("updated_at", "")), str(item.get("name", ""))),
            reverse=True,
        )
        return projects

    def list_project_ids(self) -> list[str]:
        return sorted(item["project_id"] for item in self._workspace_store.list_entries())

    def _load_snapshot_from_dir(self, project_id: str, project_dir: Path) -> dict[str, Any]:
        if self._has_unsupported_layout_artifacts(project_dir):
            raise UnsupportedProjectLayout(project_id)
        tree = load_json(project_dir / "tree.json")
        if not isinstance(tree, dict):
            raise ProjectNotFound(project_id)
        if self._schema_version(tree) != CURRENT_SCHEMA_VERSION:
            raise UnsupportedProjectLayout(project_id)
        normalized = self._normalize_snapshot_for_persistence(tree)
        normalized["project"] = self.load_meta(project_id)
        self._validate_snapshot(project_id, normalized)
        return normalized

    def _schema_version(self, snapshot: dict[str, Any]) -> int:
        try:
            return int(snapshot.get("schema_version", 0))
        except (TypeError, ValueError):
            return 0

    def _has_unsupported_layout_artifacts(self, project_dir: Path) -> bool:
        return any(
            (
                (project_dir / "nodes").exists(),
                (project_dir / "chat_state.json").exists(),
                (project_dir / "thread_state.json").exists(),
                (project_dir / "state.json").exists(),
            )
        )

    def _normalize_snapshot_for_persistence(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(snapshot)
        normalized["schema_version"] = CURRENT_SCHEMA_VERSION
        normalized["project"] = self._sanitize_meta(normalized.get("project"))
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

    def _normalize_node(self, raw_node: dict[str, Any]) -> dict[str, Any]:
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
        node["parent_id"] = parent_id if isinstance(parent_id, str) and parent_id.strip() else None
        review_node_id = node.get("review_node_id")
        node["review_node_id"] = (
            review_node_id.strip()
            if isinstance(review_node_id, str) and review_node_id.strip()
            else None
        )
        node_id = str(node.get("node_id") or "").strip()
        if node_id:
            node["node_id"] = node_id
        return node

    def _sanitize_meta(self, raw_meta: Any) -> dict[str, Any]:
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        sanitized = {key: meta.get(key) for key in _ALLOWED_META_FIELDS if key in meta}
        project_id = str(sanitized.get("id") or "").strip()
        if project_id:
            sanitized["id"] = normalize_project_id(project_id)
        name = str(sanitized.get("name") or "").strip()
        if name:
            sanitized["name"] = name
        root_goal = str(sanitized.get("root_goal") or "").strip()
        if root_goal:
            sanitized["root_goal"] = root_goal
        created_at = str(sanitized.get("created_at") or "").strip()
        if created_at:
            sanitized["created_at"] = created_at
        updated_at = str(sanitized.get("updated_at") or "").strip()
        if updated_at:
            sanitized["updated_at"] = updated_at
        return sanitized

    def _runtime_meta(self, raw_meta: dict[str, Any], folder_path: str) -> dict[str, Any]:
        sanitized = self._sanitize_meta(raw_meta)
        if "id" not in sanitized or "name" not in sanitized:
            raise UnsupportedProjectLayout(str(raw_meta.get("id") or "unattached-folder"))
        sanitized["root_goal"] = str(sanitized.get("root_goal") or sanitized["name"])
        sanitized["created_at"] = str(sanitized.get("created_at") or "")
        sanitized["updated_at"] = str(sanitized.get("updated_at") or "")
        sanitized["project_path"] = str(Path(folder_path).expanduser().resolve())
        return sanitized

    def _validate_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> None:
        tree_state = snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            raise UnsupportedProjectLayout(project_id)
        root_node_id = str(tree_state.get("root_node_id") or "").strip()
        node_index = tree_state.get("node_index")
        if not root_node_id or not isinstance(node_index, dict) or root_node_id not in node_index:
            raise UnsupportedProjectLayout(project_id)
