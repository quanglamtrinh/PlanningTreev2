from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Dict, List

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.node_store import NodeStore
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry


class ProjectStore:
    def __init__(
        self,
        paths: AppPaths,
        lock_registry: ProjectLockRegistry,
        node_store: NodeStore,
    ) -> None:
        self._paths = paths
        self._lock_registry = lock_registry
        self._node_store = node_store

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

    def chat_state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "chat_state.json"

    def thread_state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "thread_state.json"

    def create_project_files(self, meta: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
        project_id = str(meta["id"])
        with self.project_lock(project_id):
            project_dir = ensure_dir(self.project_dir(project_id))
            atomic_write_json(project_dir / "meta.json", meta)
            atomic_write_json(project_dir / "tree.json", self._normalize_snapshot_for_persistence(snapshot))
            atomic_write_json(project_dir / "chat_state.json", {})
            atomic_write_json(project_dir / "thread_state.json", {})

    def save_tree(self, project_id: str, tree: Dict[str, Any]) -> None:
        with self.project_lock(project_id):
            if not self.project_dir(project_id).exists():
                raise ProjectNotFound(project_id)
            atomic_write_json(self.tree_path(project_id), self._normalize_snapshot_for_persistence(tree))

    def save_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> None:
        self.save_tree(project_id, snapshot)

    def load_tree(self, project_id: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            tree = load_json(self.tree_path(project_id))
            if isinstance(tree, dict):
                schema_version = self._schema_version(tree)
                if schema_version == 4:
                    return self._migrate_v4_to_v5(project_id, tree)
                self._validate_tree_node_files(project_id, tree)
                return tree
            if self.state_path(project_id).exists():
                return self._migrate_v3_to_v5(project_id)
            raise ProjectNotFound(project_id)

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

    def _validate_tree_node_files(self, project_id: str, tree: Dict[str, Any]) -> None:
        node_index = tree.get("tree_state", {}).get("node_index", {})
        if not isinstance(node_index, dict):
            return
        for node_id in node_index:
            if not isinstance(node_id, str) or not node_id:
                continue
            if not self._node_store.node_exists(project_id, node_id):
                raise ValueError(
                    f"tree.json references missing or incomplete node files for node {node_id}"
                )

    def _migrate_v3_to_v5(self, project_id: str) -> Dict[str, Any]:
        old_snapshot = load_json(self.state_path(project_id))
        if not isinstance(old_snapshot, dict):
            raise ProjectNotFound(project_id)

        old_tree_state = old_snapshot.get("tree_state", {})
        if not isinstance(old_tree_state, dict):
            old_tree_state = {}
        root_node_id = str(old_tree_state.get("root_node_id") or "").strip()
        node_registry = old_tree_state.get("node_registry", [])
        if not isinstance(node_registry, list):
            node_registry = []

        node_index: Dict[str, Dict[str, Any]] = {}
        for raw_node in node_registry:
            if not isinstance(raw_node, dict):
                continue
            node = dict(raw_node)
            node_id = str(node.get("node_id") or "").strip()
            if not node_id:
                continue

            title = str(node.get("title") or "")
            description = str(node.get("description") or "")
            node.pop("title", None)
            node.pop("description", None)
            planning_thread_id = str(node.get("planning_thread_id") or "")
            execution_thread_id = str(node.get("execution_thread_id") or "")
            forked_from_node = str(node.get("planning_thread_forked_from_node") or "")
            bootstrapped_at = str(node.get("planning_thread_bootstrapped_at") or "")
            chat_session_id = str(node.get("chat_session_id") or "")
            is_superseded = bool(node.pop("is_superseded", False))

            if node_id == root_node_id:
                node_kind = "root"
            elif is_superseded:
                node_kind = "superseded"
            else:
                node_kind = "original"

            status = str(node.get("status") or "draft")
            if status == "done":
                phase = "closed"
            elif status == "in_progress":
                phase = "executing"
            else:
                phase = "planning"

            node["node_kind"] = node_kind
            node["phase"] = phase
            node["chat_session_id"] = chat_session_id or None
            node["planning_thread_id"] = planning_thread_id or None
            node["execution_thread_id"] = execution_thread_id or None
            node["planning_thread_forked_from_node"] = forked_from_node or None
            node["planning_thread_bootstrapped_at"] = bootstrapped_at or None
            node_index[node_id] = node

            node_path = self._node_store.node_dir(project_id, node_id)
            if not self._node_store.node_exists(project_id, node_id):
                if node_path.exists():
                    if node_path.is_dir():
                        shutil.rmtree(node_path)
                    else:
                        node_path.unlink()
                self._node_store.create_node_files(
                    project_id,
                    node_id,
                    task={
                        "title": title,
                        "purpose": description,
                        "responsibility": "",
                    },
                    state={
                        "phase": phase,
                        "task_confirmed": phase != "planning",
                        "briefing_confirmed": phase
                        in {"spec_review", "ready_for_execution", "executing", "closed"},
                        "spec_generated": False,
                        "spec_generation_status": "idle",
                        "spec_confirmed": phase in {"ready_for_execution", "executing", "closed"},
                        "planning_thread_id": planning_thread_id,
                        "execution_thread_id": execution_thread_id,
                        "ask_thread_id": "",
                        "planning_thread_forked_from_node": forked_from_node,
                        "planning_thread_bootstrapped_at": bootstrapped_at,
                        "chat_session_id": chat_session_id,
                    },
                )

        new_snapshot = {
            "schema_version": 5,
            "project": old_snapshot.get("project", {}),
            "tree_state": {
                "root_node_id": root_node_id,
                "active_node_id": old_tree_state.get("active_node_id"),
                "node_index": node_index,
            },
            "updated_at": old_snapshot.get("updated_at"),
        }
        atomic_write_json(self.tree_path(project_id), new_snapshot)
        self.state_path(project_id).rename(self.project_dir(project_id) / "state.json.bak")
        self._validate_tree_node_files(project_id, new_snapshot)
        return new_snapshot

    def _migrate_v4_to_v5(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_tree_node_files(project_id, snapshot)
        normalized = self._normalize_snapshot_for_persistence(snapshot)
        atomic_write_json(self.tree_path(project_id), normalized)
        return normalized

    def _schema_version(self, snapshot: Dict[str, Any]) -> int:
        try:
            return int(snapshot.get("schema_version", 0))
        except (TypeError, ValueError):
            return 0

    def _normalize_snapshot_for_persistence(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(snapshot)
        normalized["schema_version"] = 5
        tree_state = normalized.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return normalized
        node_index = tree_state.get("node_index")
        if isinstance(node_index, dict):
            for node in node_index.values():
                self._normalize_node_for_persistence(node)
        registry = tree_state.get("node_registry")
        if isinstance(registry, list):
            for node in registry:
                self._normalize_node_for_persistence(node)
        return normalized

    def _normalize_node_for_persistence(self, node: Any) -> None:
        if not isinstance(node, dict):
            return
        node.pop("title", None)
        node.pop("description", None)
