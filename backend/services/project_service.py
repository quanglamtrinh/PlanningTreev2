from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from backend.errors.app_errors import ChatNotAllowed, InvalidRequest, InvalidWorkspaceRoot, WorkspaceNotConfigured
from backend.services.snapshot_view_service import SnapshotViewService
from backend.storage.file_utils import ensure_dir, iso_now
from backend.storage.project_store import CURRENT_SCHEMA_VERSION
from backend.storage.storage import Storage


class ProjectService:
    def __init__(
        self,
        storage: Storage,
        snapshot_view_service: SnapshotViewService | None = None,
        chat_service: Any = None,
    ) -> None:
        self.storage = storage
        self._snapshot_view_service = snapshot_view_service
        self._chat_service = chat_service

    def bootstrap_status(self) -> Dict[str, bool]:
        workspace_root = self.storage.config_store.get_base_workspace_root()
        configured = False
        if workspace_root:
            try:
                self.validate_workspace_root(workspace_root)
                configured = True
            except InvalidWorkspaceRoot:
                configured = False
        return {"ready": configured, "workspace_configured": configured}

    def get_workspace_settings(self) -> Dict[str, Optional[str]]:
        return {"base_workspace_root": self.storage.config_store.get_base_workspace_root()}

    def set_workspace_root(self, base_workspace_root: str) -> Dict[str, Optional[str]]:
        resolved = self.validate_workspace_root(base_workspace_root)
        self.storage.config_store.set_base_workspace_root(str(resolved))
        return {"base_workspace_root": str(resolved)}

    def list_projects(self) -> List[Dict[str, Any]]:
        return self.storage.project_store.list_projects()

    def get_snapshot(self, project_id: str) -> Dict[str, Any]:
        snapshot = self.storage.project_store.load_snapshot(project_id)
        return self._public_snapshot(project_id, snapshot)

    def reset_to_root(self, project_id: str) -> Dict[str, Any]:
        if self._chat_service is not None and self._chat_service.has_live_turns_for_project(project_id):
            raise ChatNotAllowed("Cannot reset project while a chat turn is active.")
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            tree_state = snapshot.get("tree_state", {})
            root_id = str(tree_state.get("root_node_id") or "").strip()
            node_index = tree_state.get("node_index", {})
            root_node = node_index.get(root_id) if isinstance(node_index, dict) else None
            if root_node is None:
                raise InvalidRequest("Project snapshot is missing its root node.")

            reset_root = self._build_reset_root_node(root_node)
            snapshot["tree_state"] = {
                "root_node_id": root_id,
                "active_node_id": root_id,
                "node_index": {root_id: reset_root},
            }
            snapshot = self._persist_snapshot(project_id, snapshot)
            self.storage.chat_state_store.clear_all_sessions(project_id)
        return self._public_snapshot(project_id, snapshot)

    def delete_project(self, project_id: str) -> None:
        if self._chat_service is not None and self._chat_service.has_live_turns_for_project(project_id):
            raise ChatNotAllowed("Cannot delete project while a chat turn is active.")
        projects = self.storage.project_store.list_projects()
        project = next((p for p in projects if p.get("id") == project_id), None)
        if project is None:
            raise InvalidRequest(f"Project {project_id!r} not found.")

        workspace_root: str | None = project.get("project_workspace_root")
        self.storage.project_store.delete_project(project_id)
        if workspace_root:
            workspace_path = Path(workspace_root)
            if workspace_path.exists() and workspace_path.is_dir():
                try:
                    shutil.rmtree(workspace_path)
                except OSError:
                    pass

    def create_project(self, name: str, root_goal: str) -> Dict[str, Any]:
        cleaned_name = name.strip()
        cleaned_goal = root_goal.strip()
        if not cleaned_name:
            raise InvalidRequest("Project name is required.")
        if not cleaned_goal:
            raise InvalidRequest("Root goal is required.")

        base_workspace_root = self.storage.config_store.get_base_workspace_root()
        if not base_workspace_root:
            raise WorkspaceNotConfigured()

        resolved_root = self.validate_workspace_root(base_workspace_root)
        project_workspace_root = self._allocate_project_workspace(resolved_root, cleaned_name)

        project_id = uuid4().hex
        root_node_id = uuid4().hex
        now = iso_now()
        root_node = {
            "node_id": root_node_id,
            "parent_id": None,
            "child_ids": [],
            "title": cleaned_name,
            "description": cleaned_goal,
            "status": "draft",
            "node_kind": "root",
            "depth": 0,
            "display_order": 0,
            "hierarchical_number": "1",
            "created_at": now,
        }
        project_record = {
            "id": project_id,
            "name": cleaned_name,
            "root_goal": cleaned_goal,
            "base_workspace_root": str(resolved_root),
            "project_workspace_root": str(project_workspace_root),
            "created_at": now,
            "updated_at": now,
        }
        snapshot = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "project": dict(project_record),
            "tree_state": {
                "root_node_id": root_node_id,
                "active_node_id": root_node_id,
                "node_index": {root_node_id: root_node},
            },
            "updated_at": now,
        }
        self.storage.project_store.create_project_files(project_record, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def validate_workspace_root(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.exists():
            raise InvalidWorkspaceRoot("Workspace root does not exist.")
        if not candidate.is_dir():
            raise InvalidWorkspaceRoot("Workspace root must be a directory.")
        resolved = candidate.resolve()
        test_path = resolved / ".planningtree-write-test"
        try:
            with test_path.open("w", encoding="utf-8") as handle:
                handle.write("ok")
            test_path.unlink()
        except OSError as exc:
            raise InvalidWorkspaceRoot("Workspace root must be writable.") from exc
        return resolved

    def _allocate_project_workspace(self, base_workspace_root: Path, project_name: str) -> Path:
        slug_base = self._slugify(project_name)
        ensure_dir(base_workspace_root)
        candidate = base_workspace_root / slug_base
        suffix = 2
        while candidate.exists():
            candidate = base_workspace_root / f"{slug_base}-{suffix}"
            suffix += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate.resolve()

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        return normalized or "project"

    def _build_reset_root_node(self, root_node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "node_id": str(root_node.get("node_id") or ""),
            "parent_id": None,
            "child_ids": [],
            "title": str(root_node.get("title") or ""),
            "description": str(root_node.get("description") or ""),
            "status": "draft",
            "node_kind": "root",
            "depth": 0,
            "display_order": 0,
            "hierarchical_number": "1",
            "created_at": str(root_node.get("created_at") or iso_now()),
        }

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
