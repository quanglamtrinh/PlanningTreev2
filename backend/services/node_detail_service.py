from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from backend.errors.app_errors import ConfirmationNotAllowed, InvalidRequest, NodeNotFound
from backend.services.execution_gating import (
    AUDIT_FRAME_RECORD_MESSAGE_ID,
    AUDIT_SPEC_RECORD_MESSAGE_ID,
    append_immutable_audit_record,
    derive_execution_workflow_fields,
    require_shaping_not_frozen,
)
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

WorkflowStep = Literal["frame", "clarify", "spec"]


def _load_frame_meta_from_node_dir(node_dir: Path) -> Dict[str, Any]:
    path = node_dir / FRAME_META_FILE
    data = load_json(path, default=None)
    if not isinstance(data, dict):
        return dict(_DEFAULT_FRAME_META)
    return data


def _load_spec_meta_from_node_dir(node_dir: Path) -> Dict[str, Any]:
    path = node_dir / SPEC_META_FILE
    data = load_json(path, default=None)
    if not isinstance(data, dict):
        return dict(_DEFAULT_SPEC_META)
    return data


def _load_clarify_from_node_dir(node_dir: Path) -> Dict[str, Any] | None:
    path = node_dir / CLARIFY_FILE
    data = load_json(path, default=None)
    if not isinstance(data, dict):
        return None
    if (data.get("schema_version") or 1) < 2:
        for q in data.get("questions", []):
            if not isinstance(q, dict):
                continue
            if "answer" in q and "custom_answer" not in q:
                q["custom_answer"] = q.pop("answer")
            elif "answer" in q:
                q.pop("answer", None)
            q.pop("resolution_status", None)
            q.pop("source", None)
            q.setdefault("why_it_matters", "")
            q.setdefault("current_value", "")
            q.setdefault("options", [])
            q.setdefault("selected_option_id", None)
            q.setdefault("custom_answer", "")
            q.setdefault("allow_custom", True)
        data["schema_version"] = 2
        data.setdefault("confirmed_revision", 0)
    return data


def derive_workflow_summary_from_artifacts(
    frame_meta: Dict[str, Any],
    clarify: Dict[str, Any] | None,
    spec_meta: Dict[str, Any],
) -> Dict[str, Any]:
    frame_conf_rev = frame_meta.get("confirmed_revision", 0)
    frame_rev = frame_meta.get("revision", 0)
    frame_confirmed = frame_conf_rev >= 1
    frame_needs_reconfirm = frame_confirmed and frame_rev > frame_conf_rev
    clarify_confirmed_at = clarify.get("confirmed_at") if clarify else None

    active_step: WorkflowStep = "frame"
    if not frame_confirmed:
        active_step = "frame"
    elif frame_needs_reconfirm:
        active_step = "frame"
    elif clarify_confirmed_at is None:
        active_step = "clarify"
    else:
        active_step = "spec"

    return {
        "frame_confirmed": frame_confirmed,
        "active_step": active_step,
        "spec_confirmed": spec_meta.get("confirmed_at") is not None,
    }


def derive_workflow_summary_from_node_dir(node_dir: Path) -> Dict[str, Any]:
    frame_meta = _load_frame_meta_from_node_dir(node_dir)
    clarify = _load_clarify_from_node_dir(node_dir)
    spec_meta = _load_spec_meta_from_node_dir(node_dir)
    return derive_workflow_summary_from_artifacts(frame_meta, clarify, spec_meta)


def build_detail_state(
    storage: Storage,
    project_id: str,
    node_id: str,
    node_dir: Path,
    *,
    exec_state: Dict[str, Any] | None = None,
    node: Dict[str, Any] | None = None,
    review_state: Dict[str, Any] | None = None,
    git_checkpoint_service: Any = None,
    project_path: Path | None = None,
) -> Dict[str, Any]:
    frame_meta = _load_frame_meta_from_node_dir(node_dir)
    clarify = _load_clarify_from_node_dir(node_dir)
    spec_meta = _load_spec_meta_from_node_dir(node_dir)
    workflow = derive_workflow_summary_from_artifacts(frame_meta, clarify, spec_meta)

    frame_conf_rev = frame_meta.get("confirmed_revision", 0)
    frame_rev = frame_meta.get("revision", 0)
    frame_needs_reconfirm = workflow["frame_confirmed"] and frame_rev > frame_conf_rev
    clarify_confirmed_at = clarify.get("confirmed_at") if clarify else None
    active_step = workflow["active_step"]
    spec_src_frame = spec_meta.get("source_frame_revision", 0)
    frame_branch_ready = frame_needs_reconfirm or (
        workflow["frame_confirmed"]
        and clarify_confirmed_at is not None
        and spec_src_frame < frame_conf_rev
    )

    workflow_notice: str | None = None
    if frame_needs_reconfirm:
        workflow_notice = (
            "Clarify decisions were applied to the frame. "
            "Review and confirm the updated frame."
        )

    spec_stale = False
    if active_step == "spec" and not frame_branch_ready:
        spec_stale = spec_src_frame < frame_conf_rev

    # ── Git-aware fields ────────────────────────────────────────────
    git_ready: bool | None = None
    git_blocker_message: str | None = None
    current_head_sha: str | None = None
    task_present_in_current_workspace: bool | None = None
    if git_checkpoint_service is not None and project_path is not None:
        try:
            blockers = git_checkpoint_service.validate_guardrails(project_path)
            git_ready = len(blockers) == 0
            git_blocker_message = blockers[0] if blockers else None
            current_head_sha = git_checkpoint_service.get_head_sha(project_path)
        except Exception:
            pass  # git fields stay None
        if current_head_sha and exec_state:
            head_sha = exec_state.get("head_sha")
            if head_sha:
                try:
                    task_present_in_current_workspace = (
                        git_checkpoint_service.is_ancestor(project_path, head_sha, current_head_sha)
                        or current_head_sha == head_sha
                    )
                except Exception:
                    pass

    # ── Execution-aware derived fields ─────────────────────────────
    execution_fields = derive_execution_workflow_fields(
        storage,
        project_id,
        node_id,
        workflow=workflow,
        node=node,
        exec_state=exec_state,
        review_state=review_state,
        git_ready=git_ready,
    )
    shaping_frozen = bool(execution_fields["shaping_frozen"])
    workflow_summary = {
        **workflow,
        "execution_started": execution_fields["execution_started"],
        "execution_completed": execution_fields["execution_completed"],
        "shaping_frozen": shaping_frozen,
        "can_finish_task": execution_fields["can_finish_task"],
        "execution_status": execution_fields["execution_status"],
    }

    return {
        "node_id": node_id,
        "workflow": workflow_summary,
        "frame_confirmed": workflow["frame_confirmed"],
        "frame_confirmed_revision": frame_conf_rev,
        "frame_revision": frame_rev,
        "active_step": active_step,
        "workflow_notice": workflow_notice,
        "generation_error": None,
        "frame_branch_ready": frame_branch_ready,
        "frame_needs_reconfirm": frame_needs_reconfirm,
        "frame_read_only": shaping_frozen or (active_step != "frame" and not frame_branch_ready),
        "clarify_read_only": shaping_frozen or active_step != "clarify",
        "clarify_confirmed": clarify_confirmed_at is not None,
        "spec_read_only": shaping_frozen or active_step != "spec" or frame_branch_ready,
        "spec_stale": spec_stale,
        "spec_confirmed": workflow["spec_confirmed"],
        "initial_sha": exec_state.get("initial_sha") if exec_state else None,
        "head_sha": exec_state.get("head_sha") if exec_state else None,
        "commit_message": exec_state.get("commit_message") if exec_state else None,
        "current_head_sha": current_head_sha,
        "task_present_in_current_workspace": task_present_in_current_workspace,
        "git_ready": git_ready,
        "git_blocker_message": git_blocker_message,
        "changed_files": exec_state.get("changed_files", []) if exec_state else [],
        "execution_started": execution_fields["execution_started"],
        "execution_completed": execution_fields["execution_completed"],
        "shaping_frozen": shaping_frozen,
        "can_finish_task": execution_fields["can_finish_task"],
        "can_accept_local_review": execution_fields["can_accept_local_review"],
        "execution_status": execution_fields["execution_status"],
        "audit_writable": execution_fields["audit_writable"],
        "package_audit_ready": execution_fields["package_audit_ready"],
        "review_status": execution_fields["review_status"],
    }


def build_review_detail_state(
    node_id: str,
    *,
    review_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    review_status: str | None = None
    if isinstance(review_state, dict):
        rollup = review_state.get("rollup", {})
        if isinstance(rollup, dict):
            status = rollup.get("status")
            if isinstance(status, str) and status:
                review_status = status

    return {
        "node_id": node_id,
        "workflow": None,
        "frame_confirmed": False,
        "frame_confirmed_revision": 0,
        "frame_revision": 0,
        "active_step": "frame",
        "workflow_notice": None,
        "generation_error": None,
        "frame_branch_ready": False,
        "frame_needs_reconfirm": False,
        "frame_read_only": True,
        "clarify_read_only": True,
        "clarify_confirmed": False,
        "spec_read_only": True,
        "spec_stale": False,
        "spec_confirmed": False,
        "initial_sha": None,
        "head_sha": None,
        "changed_files": [],
        "execution_started": False,
        "execution_completed": False,
        "shaping_frozen": False,
        "can_finish_task": False,
        "can_accept_local_review": False,
        "execution_status": None,
        "audit_writable": False,
        "package_audit_ready": False,
        "review_status": review_status,
    }


class NodeDetailService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        git_checkpoint_service: Any = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._git_checkpoint_service = git_checkpoint_service

    # ── Shaping freeze guard ─────────────────────────────────────

    def _require_shaping_not_frozen(self, project_id: str, node_id: str, action: str) -> None:
        require_shaping_not_frozen(self._storage, project_id, node_id, action)

    # ── Detail state (derived from artifact metadata) ─────────────

    def get_detail_state(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id, {})
            node_kind = str(node.get("node_kind") or "")
            review_state = None
            review_node_id = node.get("review_node_id")
            if review_node_id:
                review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
            elif node_kind == "review":
                review_state = self._storage.review_state_store.read_state(project_id, node_id)
                return build_review_detail_state(
                    node_id,
                    review_state=review_state,
                )

            node_dir = self._resolve_node_dir(snapshot, node_id)
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            project = snapshot.get("project", {})
            raw_project_path = str(project.get("project_path") or "").strip()
            pp = Path(raw_project_path) if raw_project_path else None
            return build_detail_state(
                self._storage,
                project_id,
                node_id,
                node_dir,
                exec_state=exec_state,
                node=node,
                review_state=review_state,
                git_checkpoint_service=self._git_checkpoint_service,
                project_path=pp,
            )

    # ── Confirm frame ─────────────────────────────────────────────

    def confirm_frame(self, project_id: str, node_id: str) -> Dict[str, Any]:
        self._require_shaping_not_frozen(project_id, node_id, "confirm frame")
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
        append_immutable_audit_record(
            self._storage,
            project_id,
            node_id,
            message_id=AUDIT_FRAME_RECORD_MESSAGE_ID,
            content=self._build_frame_audit_record(content),
        )
        return self.get_detail_state(project_id, node_id)

    # ── Bump revision on save (called by document service) ────────

    def bump_frame_revision(self, project_id: str, node_id: str) -> None:
        """Increment frame revision when frame.md is saved. Called externally."""
        self._require_shaping_not_frozen(project_id, node_id, "save frame")
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
        self._require_shaping_not_frozen(project_id, node_id, "seed clarify")
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
        self._require_shaping_not_frozen(project_id, node_id, "update clarify")
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
        self._require_shaping_not_frozen(project_id, node_id, "apply clarify")
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
        self._require_shaping_not_frozen(project_id, node_id, "confirm spec")
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
        append_immutable_audit_record(
            self._storage,
            project_id,
            node_id,
            message_id=AUDIT_SPEC_RECORD_MESSAGE_ID,
            content=self._build_spec_audit_record(content),
        )
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
        return _load_frame_meta_from_node_dir(node_dir)

    def _save_frame_meta(self, node_dir: Path, meta: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / FRAME_META_FILE, meta)

    def _load_spec_meta(self, node_dir: Path) -> Dict[str, Any]:
        return _load_spec_meta_from_node_dir(node_dir)

    def _save_spec_meta(self, node_dir: Path, meta: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / SPEC_META_FILE, meta)

    def _load_clarify(self, node_dir: Path) -> Dict[str, Any] | None:
        return _load_clarify_from_node_dir(node_dir)

    def _save_clarify(self, node_dir: Path, clarify: Dict[str, Any]) -> None:
        atomic_write_json(node_dir / CLARIFY_FILE, clarify)

    def _build_frame_audit_record(self, content: str) -> str:
        body = content.strip() or "(empty confirmed frame)"
        return "Canonical confirmed frame snapshot:\n\n```markdown\n" + body + "\n```"

    def _build_spec_audit_record(self, content: str) -> str:
        body = content.strip() or "(empty confirmed spec)"
        return "Canonical confirmed spec snapshot:\n\n```markdown\n" + body + "\n```"

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
