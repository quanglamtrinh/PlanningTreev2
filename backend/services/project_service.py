from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.errors.app_errors import (
    InvalidRequest,
    InvalidWorkspaceRoot,
    ProjectResetNotAllowed,
    WorkspaceNotConfigured,
)
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.thread_service import ThreadService
from backend.storage.file_utils import ensure_dir, iso_now
from backend.storage.node_files import default_state, empty_briefing, empty_spec
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(
        self,
        storage: Storage,
        snapshot_view_service: SnapshotViewService | None = None,
        thread_service: ThreadService | None = None,
    ) -> None:
        self.storage = storage
        self._snapshot_view_service = snapshot_view_service
        self._thread_service = thread_service

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
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            tree_state = snapshot.get("tree_state", {})
            root_id = str(tree_state.get("root_node_id") or "").strip()
            node_index = tree_state.get("node_index", {})
            root_node = node_index.get(root_id) if isinstance(node_index, dict) else None
            if root_node is None:
                raise InvalidRequest("Project snapshot is missing its root node.")
            if self._project_has_active_turns(project_id):
                raise ProjectResetNotAllowed(
                    "Cannot reset project while planning or execution is active."
                )

            reset_root = self._build_reset_root_node(root_node)
            snapshot["tree_state"] = {
                "root_node_id": root_id,
                "active_node_id": root_id,
                "node_index": {root_id: reset_root},
            }
            snapshot = self._persist_snapshot(project_id, snapshot)

            nodes_dir = self.storage.node_store.node_dir(project_id, root_id).parent
            if nodes_dir.exists():
                for child_dir in nodes_dir.iterdir():
                    if child_dir.is_dir() and child_dir.name != root_id:
                        shutil.rmtree(child_dir)

            existing_task = self.storage.node_store.load_task(project_id, root_id)
            self.storage.node_store.save_task(
                project_id,
                root_id,
                {
                    "title": str(existing_task.get("title") or ""),
                    "purpose": str(existing_task.get("purpose") or ""),
                    "responsibility": str(existing_task.get("responsibility") or ""),
                },
            )
            self.storage.node_store.save_briefing(project_id, root_id, empty_briefing())
            self.storage.node_store.save_spec(project_id, root_id, empty_spec())
            self.storage.node_store.save_state(project_id, root_id, default_state())
            self.storage.thread_store.write_thread_state(project_id, {})
            self.storage.chat_store.write_chat_state(project_id, {})

        if self._thread_service is not None:
            try:
                snapshot = self._thread_service.initialize_root_planning_thread(project_id)
            except Exception:
                logger.warning(
                    "Failed to bootstrap root planning thread after reset for project %s",
                    project_id,
                    exc_info=True,
                )

        return self._public_snapshot(project_id, snapshot)

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
            "status": "draft",
            "phase": "planning",
            "node_kind": "root",
            "planning_mode": None,
            "depth": 0,
            "display_order": 0,
            "hierarchical_number": "1",
            "split_metadata": None,
            "chat_session_id": None,
            "planning_thread_id": None,
            "execution_thread_id": None,
            "planning_thread_forked_from_node": None,
            "planning_thread_bootstrapped_at": None,
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
            "schema_version": 5,
            "project": dict(project_record),
            "tree_state": {
                "root_node_id": root_node_id,
                "active_node_id": root_node_id,
                "node_index": {root_node_id: root_node},
            },
            "updated_at": now,
        }
        self.storage.project_store.create_project_files(project_record, snapshot)
        self.storage.node_store.create_node_files(
            project_id,
            root_node_id,
            task={
                "title": cleaned_name,
                "purpose": cleaned_goal,
                "responsibility": "",
            },
        )
        if self._thread_service is not None:
            snapshot = self._thread_service.initialize_root_planning_thread(project_id)
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
        reset_root = dict(root_node)
        reset_root.update(
            {
                "parent_id": None,
                "child_ids": [],
                "status": "draft",
                "phase": "planning",
                "node_kind": "root",
                "planning_mode": None,
                "depth": 0,
                "display_order": 0,
                "hierarchical_number": "1",
                "split_metadata": None,
                "chat_session_id": None,
                "planning_thread_id": None,
                "execution_thread_id": None,
                "planning_thread_forked_from_node": None,
                "planning_thread_bootstrapped_at": None,
            }
        )
        reset_root.pop("is_superseded", None)
        reset_root.pop("title", None)
        reset_root.pop("description", None)
        return reset_root

    def _project_has_active_turns(self, project_id: str) -> bool:
        thread_state = self.storage.thread_store.read_thread_state(project_id)
        for raw_node_state in thread_state.values():
            if not isinstance(raw_node_state, dict):
                continue
            if self._turn_state_is_active(raw_node_state.get("planning")):
                return True
            if self._turn_state_is_active(raw_node_state.get("execution")):
                return True

        chat_state = self.storage.chat_store.read_chat_state(project_id)
        for raw_session in chat_state.values():
            if not isinstance(raw_session, dict):
                continue
            active_turn_id = raw_session.get("active_turn_id")
            if isinstance(active_turn_id, str) and active_turn_id.strip():
                return True
            if str(raw_session.get("status") or "").strip().lower() == "active":
                return True

        return False

    def _turn_state_is_active(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        active_turn_id = payload.get("active_turn_id")
        if isinstance(active_turn_id, str) and active_turn_id.strip():
            return True
        return str(payload.get("status") or "").strip().lower() == "active"

    def _persist_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        now = iso_now()
        snapshot["updated_at"] = now
        snapshot.setdefault("project", {})["updated_at"] = now
        self.storage.project_store.save_snapshot(project_id, snapshot)
        self.storage.project_store.touch_meta(project_id, now)
        return snapshot

    def _public_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if self._snapshot_view_service is None:
            return snapshot
        thread_state = self.storage.thread_store.read_thread_state(project_id)
        return self._snapshot_view_service.to_public_snapshot(project_id, snapshot, thread_state)
