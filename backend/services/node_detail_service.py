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

            frame_conf_rev = frame_meta.get("confirmed_revision", 0)
            frame_rev = frame_meta.get("revision", 0)
            frame_confirmed = frame_conf_rev >= 1
            frame_needs_reconfirm = frame_confirmed and frame_rev > frame_conf_rev
            clarify_confirmed_at = clarify.get("confirmed_at") if clarify else None

            # active_step derivation (ordered rules, first match wins)
            if not frame_confirmed:
                active_step = "frame"
            elif frame_needs_reconfirm:
                active_step = "frame"
            elif clarify_confirmed_at is None:
                active_step = "clarify"
            else:
                active_step = "spec"

            workflow_notice: str | None = None
            if frame_needs_reconfirm:
                workflow_notice = (
                    "Clarify decisions were applied to the frame. "
                    "Review and confirm the updated frame."
                )

            # Read-only flags
            frame_read_only = active_step != "frame"
            clarify_read_only = active_step != "clarify"
            spec_read_only = active_step != "spec"

            # spec_stale: spec depends only on confirmed frame
            spec_stale = False
            if active_step == "spec":
                spec_src_frame = spec_meta.get("source_frame_revision", 0)
                spec_stale = spec_src_frame < frame_conf_rev

            return {
                "node_id": node_id,
                "frame_confirmed": frame_confirmed,
                "frame_confirmed_revision": frame_conf_rev,
                "frame_revision": frame_rev,
                "active_step": active_step,
                "workflow_notice": workflow_notice,
                "generation_error": None,
                "frame_needs_reconfirm": frame_needs_reconfirm,
                "frame_read_only": frame_read_only,
                "clarify_read_only": clarify_read_only,
                "clarify_confirmed": clarify_confirmed_at is not None,
                "spec_read_only": spec_read_only,
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
                    "schema_version": 2,
                    "source_frame_revision": 0,
                    "confirmed_revision": 0,
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
                selected = update.get("selected_option_id")
                custom = update.get("custom_answer")

                if selected is not None and str(selected).strip():
                    # Validate option exists
                    option_ids = {o["id"] for o in q.get("options", []) if isinstance(o, dict)}
                    if str(selected) not in option_ids:
                        raise InvalidRequest(
                            f"Invalid option '{selected}' for field '{field_name}'. "
                            f"Valid options: {', '.join(sorted(option_ids)) or '(none)'}"
                        )
                    q["selected_option_id"] = str(selected)
                    q["custom_answer"] = ""
                elif custom is not None and str(custom).strip():
                    q["custom_answer"] = str(custom)
                    q["selected_option_id"] = None
                else:
                    # Both null/empty = clear/reopen
                    q["selected_option_id"] = None
                    q["custom_answer"] = ""

            clarify["updated_at"] = iso_now()
            self._save_clarify(node_dir, clarify)
            return clarify

    def apply_clarify_to_frame(self, project_id: str, node_id: str) -> Dict[str, Any]:
        """Resolve clarify decisions back into frame.md and bump frame revision."""
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            frame_meta = self._load_frame_meta(node_dir)
            if (frame_meta.get("confirmed_revision") or 0) < 1:
                raise ConfirmationNotAllowed("Frame must be confirmed before applying clarify.")

            clarify = self._load_clarify(node_dir)
            if clarify is None:
                raise ConfirmationNotAllowed("Clarify has not been seeded yet.")

            questions = clarify.get("questions", [])
            unresolved = [
                q for q in questions
                if isinstance(q, dict)
                and q.get("selected_option_id") is None
                and not (q.get("custom_answer") or "").strip()
            ]
            if unresolved:
                raise ConfirmationNotAllowed(
                    f"{len(unresolved)} question(s) still open. Resolve all questions before applying."
                )

            # Build field_name → resolved_value map
            resolutions: Dict[str, str] = {}
            for q in questions:
                if not isinstance(q, dict):
                    continue
                selected_id = q.get("selected_option_id")
                custom = (q.get("custom_answer") or "").strip()
                if selected_id:
                    for opt in q.get("options", []):
                        if opt.get("id") == selected_id:
                            resolutions[q["field_name"]] = opt.get("value", selected_id)
                            break
                    else:
                        resolutions[q["field_name"]] = selected_id
                elif custom:
                    resolutions[q["field_name"]] = custom

            # Patch frame.md with resolved values
            frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
            content = ""
            if frame_path.exists():
                content = frame_path.read_text(encoding="utf-8")

            patched = self._patch_shaping_fields(content, resolutions)
            frame_path.write_text(patched, encoding="utf-8")

            # Bump frame revision (triggers frame_needs_reconfirm)
            frame_meta["revision"] = (frame_meta.get("revision") or 0) + 1
            self._save_frame_meta(node_dir, frame_meta)

            return self.get_detail_state(project_id, node_id)

    # ── Confirm spec ─────────────────────────────────────────────

    def confirm_spec(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            # Require frame confirmed
            frame_meta = self._load_frame_meta(node_dir)
            if (frame_meta.get("confirmed_revision") or 0) < 1:
                raise ConfirmationNotAllowed("Frame must be confirmed before confirming spec.")

            # Read spec.md content
            spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
            content = ""
            if spec_path.exists():
                content = spec_path.read_text(encoding="utf-8")

            if not content.strip():
                raise ConfirmationNotAllowed("Cannot confirm an empty spec.")

            # Update spec.meta.json — spec provenance is frame-only
            spec_meta = self._load_spec_meta(node_dir)
            spec_meta["source_frame_revision"] = frame_meta.get("confirmed_revision", 0)
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
        # v1 → v2 migration: status-based → choice-based
        if (data.get("schema_version") or 1) < 2:
            for q in data.get("questions", []):
                if not isinstance(q, dict):
                    continue
                # Map answer → custom_answer
                if "answer" in q and "custom_answer" not in q:
                    q["custom_answer"] = q.pop("answer")
                elif "answer" in q:
                    q.pop("answer", None)
                # Drop resolution_status
                q.pop("resolution_status", None)
                q.pop("source", None)
                # Add defaults for new fields
                q.setdefault("why_it_matters", "")
                q.setdefault("current_value", "")
                q.setdefault("options", [])
                q.setdefault("selected_option_id", None)
                q.setdefault("custom_answer", "")
                q.setdefault("allow_custom", True)
            data["schema_version"] = 2
            data.setdefault("confirmed_revision", 0)
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
                    q["custom_answer"] = old.get("custom_answer", "")
                    # Preserve selected_option_id — deterministic seed has empty
                    # options, but AI regenerate will later merge new options with
                    # this selection. Keeping it on disk avoids data loss between
                    # frame re-confirm and AI regenerate completion.
                    old_selected = old.get("selected_option_id")
                    if old_selected is not None:
                        q["selected_option_id"] = old_selected

        # Zero questions = auto-confirm per workflow contract
        auto_confirm = len(new_questions) == 0
        now = iso_now()
        clarify: Dict[str, Any] = {
            "schema_version": 2,
            "source_frame_revision": confirmed_revision,
            "confirmed_revision": 1 if auto_confirm else 0,
            "confirmed_at": now if auto_confirm else None,
            "questions": new_questions,
            "updated_at": now,
        }
        self._save_clarify(node_dir, clarify)

    def _patch_shaping_fields(self, content: str, resolutions: Dict[str, str]) -> str:
        """Patch resolved values into the Task-Shaping Fields section of frame markdown."""
        if not resolutions:
            return content
        lines = content.split("\n")
        in_section = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^#\s+Task[- ]Shaping\s+Fields", stripped, re.IGNORECASE):
                in_section = True
                continue
            if in_section and stripped.startswith("#"):
                break
            if not in_section:
                continue
            m = re.match(r"^(-\s+)(.+?):\s*(.*)", line)
            if m:
                field_name = m.group(2).strip()
                if field_name in resolutions:
                    lines[i] = f"{m.group(1)}{field_name}: {resolutions[field_name]}"
        return "\n".join(lines)

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
                "why_it_matters": "",
                "current_value": "",
                "options": [],
                "selected_option_id": None,
                "custom_answer": "",
                "allow_custom": True,
            })

        return questions
