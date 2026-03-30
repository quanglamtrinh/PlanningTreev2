from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.config.app_config import get_codex_cmd
from backend.errors.app_errors import ChatNotAllowed, InvalidProjectFolder, InvalidRequest, ProjectNotFound
from backend.services import planningtree_workspace
from backend.services.snapshot_view_service import SnapshotViewService
from backend.storage.file_utils import iso_now
from backend.storage.project_store import CURRENT_SCHEMA_VERSION
from backend.storage.storage import Storage


class ProjectService:
    def __init__(
        self,
        storage: Storage,
        snapshot_view_service: SnapshotViewService | None = None,
        chat_service: Any = None,
        git_checkpoint_service: Any = None,
        execution_audit_v2_enabled: bool = False,
    ) -> None:
        self.storage = storage
        self._snapshot_view_service = snapshot_view_service
        self._chat_service = chat_service
        self._git_checkpoint_service = git_checkpoint_service
        self._execution_audit_v2_enabled = bool(execution_audit_v2_enabled)

    def bootstrap_status(self) -> dict[str, Any]:
        codex_path = get_codex_cmd()
        return {
            "ready": True,
            "workspace_configured": True,
            "codex_available": codex_path is not None,
            "codex_path": codex_path,
            "execution_audit_v2_enabled": self._execution_audit_v2_enabled,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        projects = self.storage.project_store.list_projects()
        if self._git_checkpoint_service is not None:
            for p in projects:
                project_path = p.get("project_path")
                if project_path:
                    try:
                        p["git_initialized"] = self._git_checkpoint_service.probe_git_initialized(
                            Path(project_path)
                        )
                    except Exception:
                        p["git_initialized"] = False
                else:
                    p["git_initialized"] = False
        return projects

    def attach_project_folder(self, folder_path: str) -> dict[str, Any]:
        resolved_folder = self.validate_project_folder(folder_path)
        existing_project_id = self.storage.workspace_store.find_project_id_by_folder(str(resolved_folder))
        if existing_project_id:
            snapshot = self.storage.project_store.load_snapshot(existing_project_id)
            self._sync_snapshot_tree(snapshot, resolved_folder)
            return self._public_snapshot(existing_project_id, snapshot)

        planningtree_dir = self.storage.project_store.project_dir_for_folder(resolved_folder)
        if not planningtree_dir.exists():
            snapshot = self._initialize_project_folder(resolved_folder)
            project_id = str(snapshot["project"]["id"])
            self.storage.workspace_store.upsert_entry(project_id, str(resolved_folder))
            snapshot = self.storage.project_store.load_snapshot(project_id)
            return self._public_snapshot(project_id, snapshot)

        existing_meta = self.storage.project_store.load_meta_from_folder(str(resolved_folder))
        project_id = str(existing_meta["id"])
        self.storage.workspace_store.upsert_entry(project_id, str(resolved_folder))
        snapshot = self.storage.project_store.load_snapshot(project_id)
        self._sync_snapshot_tree(snapshot, resolved_folder)
        return self._public_snapshot(project_id, snapshot)

    def get_snapshot(self, project_id: str) -> dict[str, Any]:
        snapshot = self.storage.project_store.load_snapshot(project_id)
        self._sync_snapshot_tree(snapshot)
        return self._public_snapshot(project_id, snapshot)

    def reset_to_root(self, project_id: str) -> dict[str, Any]:
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
            self._sync_snapshot_tree(snapshot)
        return self._public_snapshot(project_id, snapshot)

    def delete_project(self, project_id: str) -> None:
        if self._chat_service is not None and self._chat_service.has_live_turns_for_project(project_id):
            raise ChatNotAllowed("Cannot remove project while a chat turn is active.")
        try:
            self.storage.workspace_store.get_folder_path(project_id)
        except ProjectNotFound:
            raise
        self.storage.workspace_store.remove_project(project_id)

    def validate_project_folder(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.exists():
            raise InvalidProjectFolder("Selected folder does not exist.")
        if not candidate.is_dir():
            raise InvalidProjectFolder("Selected path must be a directory.")
        resolved = candidate.resolve()
        test_path = resolved / ".planningtree-write-test"
        try:
            with test_path.open("w", encoding="utf-8") as handle:
                handle.write("ok")
            test_path.unlink(missing_ok=True)
        except OSError as exc:
            raise InvalidProjectFolder("Selected folder must be writable.") from exc
        return resolved

    def _initialize_project_folder(self, folder_path: Path) -> dict[str, Any]:
        project_id = uuid4().hex
        root_node_id = uuid4().hex
        now = iso_now()
        folder_name = folder_path.name.strip() or str(folder_path)
        root_goal = folder_name
        root_node = {
            "node_id": root_node_id,
            "parent_id": None,
            "child_ids": [],
            "title": folder_name,
            "description": "",
            "status": "draft",
            "node_kind": "root",
            "depth": 0,
            "display_order": 0,
            "hierarchical_number": "1",
            "created_at": now,
        }
        project_record = {
            "id": project_id,
            "name": folder_name,
            "root_goal": root_goal,
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
        self.storage.project_store.create_project_files(str(folder_path), project_record, snapshot)
        self._sync_snapshot_tree(snapshot, folder_path)
        return snapshot

    def _build_reset_root_node(self, root_node: dict[str, Any]) -> dict[str, Any]:
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

    def _persist_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        snapshot["updated_at"] = iso_now()
        self.storage.project_store.save_snapshot(project_id, snapshot)
        meta = self.storage.project_store.touch_meta(project_id, snapshot["updated_at"])
        snapshot["project"] = meta
        return snapshot

    def _public_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        if self._snapshot_view_service is None:
            return snapshot
        return self._snapshot_view_service.to_public_snapshot(project_id, snapshot)

    def _sync_snapshot_tree(
        self,
        snapshot: dict[str, Any],
        project_path: Path | None = None,
    ) -> None:
        resolved_path = project_path
        if resolved_path is None:
            project = snapshot.get("project", {})
            if isinstance(project, dict):
                raw_project_path = str(project.get("project_path") or "").strip()
                if raw_project_path:
                    resolved_path = Path(raw_project_path)
        if resolved_path is None:
            return
        planningtree_workspace.sync_snapshot_tree(resolved_path, snapshot)
