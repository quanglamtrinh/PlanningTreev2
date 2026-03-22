from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from backend.errors.app_errors import ConfirmationNotAllowed, InvalidRequest, NodeNotFound
from backend.services import planningtree_workspace
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.storage import Storage

FRAME_META_FILE = "frame.meta.json"
SPEC_META_FILE = "spec.meta.json"

_DEFAULT_FRAME_META: Dict[str, Any] = {
    "revision": 0,
    "confirmed_revision": 0,
    "confirmed_at": None,
}

_DEFAULT_SPEC_META: Dict[str, Any] = {
    "source_frame_revision": 0,
    "source_clarify_revision": 0,
    "confirmed_at": None,
}


class NodeDetailService:
    def __init__(self, storage: Storage, tree_service: TreeService) -> None:
        self._storage = storage
        self._tree_service = tree_service

    # ── Detail state (derived from artifact metadata) ─────────────

    def get_detail_state(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            frame_meta = self._load_frame_meta(node_dir)
            clarify = self._load_clarify(node_dir)
            spec_meta = self._load_spec_meta(node_dir)

            frame_confirmed = (frame_meta.get("confirmed_revision") or 0) >= 1
            clarify_confirmed_at = clarify.get("confirmed_at") if clarify else None
            clarify_unlocked = frame_confirmed
            clarify_stale = False
            if clarify_unlocked and clarify is not None:
                source_rev = clarify.get("source_frame_revision", 0)
                frame_conf_rev = frame_meta.get("confirmed_revision", 0)
                clarify_stale = source_rev < frame_conf_rev

            spec_unlocked = clarify_confirmed_at is not None
            spec_stale = False
            if spec_unlocked:
                spec_src_frame = spec_meta.get("source_frame_revision", 0)
                spec_src_clarify = spec_meta.get("source_clarify_revision", 0)
                frame_conf_rev = frame_meta.get("confirmed_revision", 0)
                spec_stale = spec_src_frame < frame_conf_rev or (
                    clarify is not None and spec_src_clarify < (clarify.get("source_frame_revision", 0))
                )

            return {
                "node_id": node_id,
                "frame_confirmed": frame_confirmed,
                "frame_confirmed_revision": frame_meta.get("confirmed_revision", 0),
                "frame_revision": frame_meta.get("revision", 0),
                "clarify_unlocked": clarify_unlocked,
                "clarify_stale": clarify_stale,
                "clarify_confirmed": clarify_confirmed_at is not None,
                "spec_unlocked": spec_unlocked,
                "spec_stale": spec_stale,
                "spec_confirmed": spec_meta.get("confirmed_at") is not None,
            }

    # ── Confirm frame ─────────────────────────────────────────────

    def confirm_frame(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            # Read frame.md content
            frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
            content = ""
            if frame_path.exists():
                content = frame_path.read_text(encoding="utf-8")

            if not content.strip():
                raise ConfirmationNotAllowed("Cannot confirm an empty frame.")

            # Bump revision metadata
            frame_meta = self._load_frame_meta(node_dir)
            revision = frame_meta.get("revision", 0)
            if revision < 1:
                revision = 1
            frame_meta["confirmed_revision"] = revision
            frame_meta["confirmed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_frame_meta(node_dir, frame_meta)

            # Extract title from # Task Title section and sync to node.title
            extracted_title = self._extract_task_title(content)
            if extracted_title:
                node_index = self._tree_service.node_index(snapshot)
                node = node_index.get(node_id)
                if node and node.get("title") != extracted_title:
                    node["title"] = extracted_title
                    snapshot = self._persist_snapshot(project_id, snapshot)
                    self._sync_snapshot_tree(snapshot)

            return self.get_detail_state(project_id, node_id)

    # ── Bump revision on save (called by document service) ────────

    def bump_frame_revision(self, project_id: str, node_id: str) -> None:
        """Increment frame revision when frame.md is saved. Called externally."""
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            frame_meta = self._load_frame_meta(node_dir)
            frame_meta["revision"] = (frame_meta.get("revision") or 0) + 1
            self._save_frame_meta(node_dir, frame_meta)

    # ── Internal helpers ──────────────────────────────────────────

    def _extract_task_title(self, markdown_content: str) -> str | None:
        """Extract the first line of content under '# Task Title' section."""
        pattern = r"^#\s+Task\s+Title\s*$"
        lines = markdown_content.split("\n")
        for i, line in enumerate(lines):
            if re.match(pattern, line.strip(), re.IGNORECASE):
                # Take next non-empty line as the title
                for j in range(i + 1, len(lines)):
                    candidate = lines[j].strip()
                    if candidate.startswith("#"):
                        break
                    if candidate:
                        return candidate
                break
        return None

    def _resolve_node_dir(self, snapshot: Dict[str, Any], node_id: str) -> Path:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise InvalidRequest("Project snapshot is missing project_path.")
        project_path = Path(raw_path)
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
        if node_dir is None:
            raise NodeNotFound(node_id)
        return node_dir

    def _require_node(self, snapshot: Dict[str, Any], node_id: str) -> None:
        tree_state = snapshot.get("tree_state", {})
        node_index = tree_state.get("node_index", {}) if isinstance(tree_state, dict) else {}
        if not isinstance(node_index, dict) or node_id not in node_index:
            raise NodeNotFound(node_id)

    def _persist_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self._storage.project_store.save_snapshot(project_id, snapshot)
        return self._storage.project_store.load_snapshot(project_id)

    def _sync_snapshot_tree(self, snapshot: Dict[str, Any]) -> None:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if raw_path:
            planningtree_workspace.sync_snapshot_tree(Path(raw_path), snapshot)

    def _load_frame_meta(self, node_dir: Path) -> Dict[str, Any]:
        path = node_dir / FRAME_META_FILE
        data = load_json(path, default=None)
        if not isinstance(data, dict):
            return dict(_DEFAULT_FRAME_META)
        return data

    def _save_frame_meta(self, node_dir: Path, meta: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / FRAME_META_FILE, meta)

    def _load_spec_meta(self, node_dir: Path) -> Dict[str, Any]:
        path = node_dir / SPEC_META_FILE
        data = load_json(path, default=None)
        if not isinstance(data, dict):
            return dict(_DEFAULT_SPEC_META)
        return data

    def _load_clarify(self, node_dir: Path) -> Dict[str, Any] | None:
        path = node_dir / "clarify.json"
        data = load_json(path, default=None)
        if not isinstance(data, dict):
            return None
        return data
