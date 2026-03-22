from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.errors.app_errors import ConfirmationNotAllowed, InvalidRequest, NodeNotFound
from backend.services import planningtree_workspace
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, iso_now, load_json
from backend.storage.storage import Storage

FRAME_META_FILE = "frame.meta.json"
SPEC_META_FILE = "spec.meta.json"
CLARIFY_FILE = "clarify.json"

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
                clarify_conf_rev = (clarify.get("confirmed_revision") or 0) if clarify else 0
                spec_stale = spec_src_frame < frame_conf_rev or (
                    spec_src_clarify < clarify_conf_rev
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

            # Bump revision metadata and snapshot confirmed content
            frame_meta = self._load_frame_meta(node_dir)
            revision = frame_meta.get("revision", 0)
            if revision < 1:
                revision = 1
            frame_meta["confirmed_revision"] = revision
            frame_meta["confirmed_at"] = datetime.now(timezone.utc).isoformat()
            frame_meta["confirmed_content"] = content
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
                    # Re-resolve node_dir since title sync may have renamed it
                    node_dir = self._resolve_node_dir(snapshot, node_id)

            # Seed clarify from unresolved shaping fields
            self._seed_clarify_internal(node_dir, content, frame_meta)

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

    # ── Clarify ────────────────────────────────────────────────────

    def get_clarify(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            clarify = self._load_clarify(node_dir)
            if clarify is None:
                return {
                    "schema_version": 1,
                    "source_frame_revision": 0,
                    "confirmed_at": None,
                    "questions": [],
                    "updated_at": None,
                }
            return clarify

    def seed_clarify(self, project_id: str, node_id: str) -> Dict[str, Any]:
        """Create or re-seed clarify.json from unresolved shaping fields in frame.md."""
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            frame_meta = self._load_frame_meta(node_dir)

            frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
            content = ""
            if frame_path.exists():
                content = frame_path.read_text(encoding="utf-8")

            self._seed_clarify_internal(node_dir, content, frame_meta)
            return self._load_clarify(node_dir) or self.get_clarify(project_id, node_id)

    def update_clarify_answers(
        self, project_id: str, node_id: str, answers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Batch-update answers in clarify.json."""
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            clarify = self._load_clarify(node_dir)
            if clarify is None:
                raise InvalidRequest("Clarify has not been seeded yet.")

            questions = clarify.get("questions", [])
            by_field = {q["field_name"]: q for q in questions if isinstance(q, dict)}

            unknown_fields = []
            for update in answers:
                field_name = str(update.get("field_name", "")).strip()
                if not field_name:
                    continue
                if field_name not in by_field:
                    unknown_fields.append(field_name)
                    continue
            if unknown_fields:
                raise InvalidRequest(
                    f"Unknown clarify field(s): {', '.join(unknown_fields)}"
                )

            for update in answers:
                field_name = str(update.get("field_name", "")).strip()
                if not field_name or field_name not in by_field:
                    continue
                q = by_field[field_name]
                if "answer" in update:
                    q["answer"] = str(update["answer"])
                if "resolution_status" in update:
                    status = str(update["resolution_status"]).strip()
                    if status in ("open", "answered", "assumed", "deferred"):
                        q["resolution_status"] = status

            clarify["updated_at"] = iso_now()
            self._save_clarify(node_dir, clarify)
            return clarify

    def confirm_clarify(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            frame_meta = self._load_frame_meta(node_dir)
            if (frame_meta.get("confirmed_revision") or 0) < 1:
                raise ConfirmationNotAllowed("Frame must be confirmed before confirming clarify.")

            clarify = self._load_clarify(node_dir)
            if clarify is None:
                raise ConfirmationNotAllowed("Clarify has not been seeded yet.")

            questions = clarify.get("questions", [])
            unresolved = [q for q in questions if isinstance(q, dict) and q.get("resolution_status") == "open"]
            if unresolved:
                raise ConfirmationNotAllowed(
                    f"{len(unresolved)} question(s) still open. Resolve all questions before confirming."
                )

            clarify["confirmed_revision"] = (clarify.get("confirmed_revision") or 0) + 1
            clarify["confirmed_at"] = iso_now()
            clarify["updated_at"] = iso_now()
            self._save_clarify(node_dir, clarify)

            return self.get_detail_state(project_id, node_id)

    # ── Confirm spec ─────────────────────────────────────────────

    def confirm_spec(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            # Require clarify confirmed (which implies frame confirmed)
            clarify = self._load_clarify(node_dir)
            if clarify is None or clarify.get("confirmed_at") is None:
                raise ConfirmationNotAllowed("Clarify must be confirmed before confirming spec.")

            # Read spec.md content
            spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
            content = ""
            if spec_path.exists():
                content = spec_path.read_text(encoding="utf-8")

            if not content.strip():
                raise ConfirmationNotAllowed("Cannot confirm an empty spec.")

            # Update spec.meta.json
            frame_meta = self._load_frame_meta(node_dir)
            spec_meta = self._load_spec_meta(node_dir)
            spec_meta["source_frame_revision"] = frame_meta.get("confirmed_revision", 0)
            spec_meta["source_clarify_revision"] = clarify.get("confirmed_revision", 0)
            spec_meta["confirmed_at"] = iso_now()
            self._save_spec_meta(node_dir, spec_meta)

            return self.get_detail_state(project_id, node_id)

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

    def _save_spec_meta(self, node_dir: Path, meta: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / SPEC_META_FILE, meta)

    def _load_clarify(self, node_dir: Path) -> Dict[str, Any] | None:
        path = node_dir / CLARIFY_FILE
        data = load_json(path, default=None)
        if not isinstance(data, dict):
            return None
        return data

    def _save_clarify(self, node_dir: Path, clarify: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / CLARIFY_FILE, clarify)

    def _seed_clarify_internal(
        self, node_dir: Path, frame_content: str, frame_meta: Dict[str, Any]
    ) -> None:
        """Seed or re-seed clarify.json. Called inside an existing lock."""
        new_questions = self._extract_unresolved_shaping_fields(frame_content)
        confirmed_revision = frame_meta.get("confirmed_revision", 0)

        existing = self._load_clarify(node_dir)
        if existing is not None:
            old_by_field = {q["field_name"]: q for q in existing.get("questions", []) if isinstance(q, dict)}
            for q in new_questions:
                old = old_by_field.get(q["field_name"])
                if old:
                    q["answer"] = old.get("answer", "")
                    q["resolution_status"] = old.get("resolution_status", "open")

        clarify: Dict[str, Any] = {
            "schema_version": 1,
            "source_frame_revision": confirmed_revision,
            "confirmed_revision": 0,
            "confirmed_at": None,
            "questions": new_questions,
            "updated_at": iso_now(),
        }
        self._save_clarify(node_dir, clarify)

    def _extract_unresolved_shaping_fields(self, markdown_content: str) -> List[Dict[str, Any]]:
        """Parse '# Task-Shaping Fields' section for unresolved fields.

        Format: ``- field name: value`` — if value is empty, the field is unresolved.
        """
        lines = markdown_content.split("\n")
        in_section = False
        questions: List[Dict[str, Any]] = []

        for line in lines:
            stripped = line.strip()
            if re.match(r"^#\s+Task[- ]Shaping\s+Fields", stripped, re.IGNORECASE):
                in_section = True
                continue
            if in_section and stripped.startswith("#"):
                break
            if not in_section:
                continue

            # Parse ``- field_name: value``
            m = re.match(r"^-\s+(.+?):\s*(.*)", stripped)
            if not m:
                continue
            field_name = m.group(1).strip()
            value = m.group(2).strip()
            if not field_name:
                continue
            # Only create questions for fields with no value
            if value:
                continue
            questions.append({
                "field_name": field_name,
                "question": f"What should '{field_name}' be for this task?",
                "answer": "",
                "resolution_status": "open",
            })

        return questions
