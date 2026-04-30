from __future__ import annotations

import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from backend.ai.split_context_builder import build_split_context
from backend.business.workflow_v2.artifact_turn_runner import WorkflowArtifactTurnRunnerV2
from backend.ai.split_prompt_builder import (
    build_hidden_retry_feedback,
    build_split_attempt_prompt,
    split_payload_issues,
    validate_split_payload,
)
from backend.errors.app_errors import (
    NodeNotFound,
    ProjectNotFound,
    SplitBackendUnavailable,
    SplitInvalidResponse,
    SplitNotAllowed,
)
from backend.services import planningtree_workspace
from backend.services.execution_gating import require_shaping_not_frozen
from backend.services.node_detail_service import (
    _load_frame_meta_from_node_dir,
    derive_workflow_summary_from_node_dir,
)
from backend.services.tree_service import TreeService
from backend.split_contract import FlatSubtaskPayload, ServiceSplitMode
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage

_RETRY_LIMIT = 2
_STALE_JOB_MESSAGE = "This split was interrupted because the server restarted before it completed."
logger = logging.getLogger(__name__)


class SplitCommitResult(TypedDict):
    initialSha: str
    headSha: str
    commitMessage: str
    committed: bool


class SplitService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        split_timeout: int,
        artifact_turn_runner: WorkflowArtifactTurnRunnerV2,
        git_checkpoint_service: Any = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._split_timeout = int(split_timeout)
        self._git_checkpoint_service = git_checkpoint_service
        self._artifact_turn_runner = artifact_turn_runner
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}

    def split_node(self, project_id: str, node_id: str, mode: ServiceSplitMode) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            require_shaping_not_frozen(self._storage, project_id, node_id, "split")
            self._validate_split_eligibility(snapshot, node, node_by_id)
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.workflow_domain_store.read_split_jobs(project_id))
            if split_state.get("active_job"):
                raise SplitNotAllowed("A split is already active for this project.")
            workspace_root = self._workspace_root_from_snapshot(snapshot)
        self._ensure_split_thread(project_id, node_id, workspace_root)
        job_id = new_id("split")
        started_at = iso_now()

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(snapshot, node, node_by_id)
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.workflow_domain_store.read_split_jobs(project_id))
            if split_state.get("active_job"):
                raise SplitNotAllowed("A split is already active for this project.")
            split_state["active_job"] = {
                "job_id": job_id,
                "node_id": node_id,
                "mode": mode,
                "started_at": started_at,
            }
            split_state["last_error"] = None
            self._storage.workflow_domain_store.write_split_jobs(project_id, split_state)
            self._mark_live_job(project_id, job_id)

        threading.Thread(
            target=self._run_background_split,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "mode": mode,
                "job_id": job_id,
                "started_at": started_at,
            },
            daemon=True,
        ).start()

        return {
            "status": "accepted",
            "job_id": job_id,
            "node_id": node_id,
            "mode": mode,
        }

    def get_split_status(self, project_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            self._storage.project_store.load_snapshot(project_id)
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.workflow_domain_store.read_split_jobs(project_id))
            return self._status_payload(split_state)

    def _run_background_split(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: ServiceSplitMode,
        job_id: str,
        started_at: str,
    ) -> None:
        try:
            payload = self._generate_split_payload(project_id, node_id, mode)
            lineage_targets = self._materialize_split_payload(project_id, node_id, payload)
            self._bootstrap_split_lineage(project_id, node_id, lineage_targets)
            self._refresh_ask_context(project_id, node_id)
            self._mark_job_completed(project_id, job_id)
        except ProjectNotFound:
            self._clear_live_job(project_id, job_id)
        except Exception as exc:
            self._mark_job_failed(project_id, job_id, node_id, mode, started_at, str(exc))

    def _generate_split_payload(
        self,
        project_id: str,
        node_id: str,
        mode: ServiceSplitMode,
    ) -> FlatSubtaskPayload:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            task_context = build_split_context(snapshot, node, node_by_id)
            if workspace_root:
                node_dir = planningtree_workspace.resolve_node_dir(
                    Path(workspace_root), snapshot, node_id
                )
                if node_dir is not None:
                    frame_meta = _load_frame_meta_from_node_dir(node_dir)

                    frame_content = str(frame_meta.get("confirmed_content") or "").strip()
                    if not frame_content:
                        frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
                        if frame_path.exists():
                            frame_content = frame_path.read_text(encoding="utf-8").strip()

                    if frame_content:
                        task_context["frame_content"] = frame_content
        thread_id = self._ensure_split_thread(project_id, node_id, workspace_root)

        retry_feedback: str | None = None
        last_issues = ["No valid split_result payload was captured."]
        for attempt in range(_RETRY_LIMIT + 1):
            prompt = build_split_attempt_prompt(mode, task_context, retry_feedback)
            result = self._artifact_turn_runner.run_prompt(
                project_id=project_id,
                node_id=node_id,
                thread_id=thread_id,
                prompt=prompt,
                artifact_kind="split",
                cwd=workspace_root,
                timeout_sec=self._split_timeout,
            )
            tool_calls = result.get("tool_calls", [])
            payload = self._extract_split_payload(
                tool_calls,
                stdout=str(result.get("stdout", "") or ""),
            )
            if payload and validate_split_payload(mode, payload):
                return payload  # type: ignore[return-value]

            last_issues = split_payload_issues(mode, payload or {})
            if attempt >= _RETRY_LIMIT:
                raise SplitInvalidResponse(last_issues)
            retry_feedback = build_hidden_retry_feedback(mode, last_issues)

        raise SplitInvalidResponse(last_issues)

    def _materialize_split_payload(
        self,
        project_id: str,
        node_id: str,
        payload: FlatSubtaskPayload,
    ) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            parent = node_by_id.get(node_id)
            if parent is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(snapshot, parent, node_by_id)

            subtasks = payload["subtasks"]
            if not subtasks:
                raise SplitInvalidResponse(["payload.subtasks must contain at least one item"])

            now = iso_now()
            inherited_locked = parent.get("status") == "locked" or self._tree_service.has_locked_ancestor(parent, node_by_id)
            parent_hnum = str(parent.get("hierarchical_number") or "1")
            parent_depth = int(parent.get("depth", 0) or 0)

            # â”€â”€ Create only the first child â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            first_subtask = subtasks[0]
            first_child_id = uuid4().hex
            first_child = {
                "node_id": first_child_id,
                "parent_id": node_id,
                "child_ids": [],
                "title": first_subtask["title"],
                "description": _build_flat_subtask_description(first_subtask),
                "status": "locked" if inherited_locked else "ready",
                "node_kind": "original",
                "depth": parent_depth + 1,
                "display_order": 0,
                "hierarchical_number": f"{parent_hnum}.1",
                "created_at": now,
            }
            parent.setdefault("child_ids", []).append(first_child_id)
            snapshot["tree_state"]["node_index"][first_child_id] = first_child
            node_by_id[first_child_id] = first_child

            # â”€â”€ Create real review node â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            review_node_id = uuid4().hex
            parent_title = str(parent.get("title") or "")
            review_node = {
                "node_id": review_node_id,
                "parent_id": node_id,
                "child_ids": [],
                "title": "Review",
                "description": f"Review node for {parent_hnum} {parent_title}".strip(),
                "status": "ready",
                "node_kind": "review",
                "depth": parent_depth + 1,
                "display_order": 0,
                "hierarchical_number": f"{parent_hnum}.R",
                "created_at": now,
            }
            # Review node is NOT in parent.child_ids â€” stored via review_node_id
            snapshot["tree_state"]["node_index"][review_node_id] = review_node
            node_by_id[review_node_id] = review_node
            parent["review_node_id"] = review_node_id

            # â”€â”€ Compute K0 baseline SHA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                from backend.services.workspace_sha import compute_workspace_sha
                k0_sha = compute_workspace_sha(Path(workspace_root))
            else:
                k0_sha = "sha256:" + "0" * 64

            # â”€â”€ Build pending siblings manifest â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            pending_siblings = []
            for index, subtask in enumerate(subtasks[1:], start=2):
                pending_siblings.append({
                    "index": index,
                    "title": subtask["title"],
                    "objective": subtask["objective"],
                    "materialized_node_id": None,
                })

            # â”€â”€ Capture git HEAD for first-sibling baseline â”€â”€â”€â”€â”€â”€â”€â”€â”€
            k0_git_head_sha: str | None = None
            if self._git_checkpoint_service is not None and workspace_root:
                try:
                    if self._git_checkpoint_service.probe_git_initialized(Path(workspace_root)):
                        k0_git_head_sha = self._git_checkpoint_service.capture_head_sha(
                            Path(workspace_root)
                        )
                except Exception:
                    logger.warning("Failed to capture k0_git_head_sha at split time")

            # â”€â”€ Write review_state.json â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            review_state: dict[str, Any] = {
                "checkpoints": [
                    {
                        "label": "K0",
                        "sha": k0_sha,
                        "summary": None,
                        "source_node_id": None,
                        "accepted_at": now,
                    }
                ],
                "rollup": {
                    "status": "pending",
                    "summary": None,
                    "sha": None,
                    "accepted_at": None,
                },
                "pending_siblings": pending_siblings,
                "k0_git_head_sha": k0_git_head_sha,
            }
            self._storage.workflow_domain_store.write_review(
                project_id, review_node_id, review_state
            )

            # â”€â”€ Update parent and snapshot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if parent.get("status") in {"ready", "in_progress"}:
                parent["status"] = "draft"

            snapshot["tree_state"]["active_node_id"] = first_child_id
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            snapshot["project"] = self._storage.project_store.touch_meta(project_id, now)
            self._sync_snapshot_tree(snapshot)
            split_commit = self._commit_split_projection(
                workspace_root=workspace_root,
                parent_hierarchical_number=parent_hnum,
                parent_title=parent_title,
            )
            split_commit_sha: str | None = None
            if split_commit is not None and split_commit["committed"]:
                split_commit_sha = split_commit["headSha"]
                review_state["k0_git_head_sha"] = split_commit_sha
            if split_commit_sha:
                self._storage.workflow_domain_store.write_review(
                    project_id, review_node_id, review_state
                )
            return {
                "workspace_root": workspace_root,
                "review_node_id": review_node_id,
                "first_child_id": first_child_id,
                "split_commit_sha": split_commit_sha,
            }

    def _ensure_split_thread(self, project_id: str, node_id: str, workspace_root: str | None) -> str:
        return str(
            self._artifact_turn_runner.ensure_ask_thread(
                project_id=project_id,
                node_id=node_id,
                workspace_root=workspace_root,
                artifact_kind="split",
            )
        )

    def _status_payload(self, split_state: dict[str, Any]) -> dict[str, Any]:
        active_job = split_state.get("active_job")
        if isinstance(active_job, dict):
            return {
                "status": "active",
                "job_id": active_job.get("job_id"),
                "node_id": active_job.get("node_id"),
                "mode": active_job.get("mode"),
                "started_at": active_job.get("started_at"),
                "completed_at": None,
                "error": None,
            }

        last_error = split_state.get("last_error")
        if isinstance(last_error, dict):
            return {
                "status": "failed",
                "job_id": last_error.get("job_id"),
                "node_id": last_error.get("node_id"),
                "mode": last_error.get("mode"),
                "started_at": last_error.get("started_at"),
                "completed_at": last_error.get("completed_at"),
                "error": last_error.get("error"),
            }

        last_completed = split_state.get("last_completed")
        if isinstance(last_completed, dict):
            return {
                "status": "idle",
                "job_id": last_completed.get("job_id"),
                "node_id": last_completed.get("node_id"),
                "mode": last_completed.get("mode"),
                "started_at": last_completed.get("started_at"),
                "completed_at": last_completed.get("completed_at"),
                "error": None,
            }

        return {
            "status": "idle",
            "job_id": None,
            "node_id": None,
            "mode": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    def _reconcile_stale_job_locked(self, project_id: str, split_state: dict[str, Any]) -> dict[str, Any]:
        active_job = split_state.get("active_job")
        if not isinstance(active_job, dict):
            return split_state
        job_id = active_job.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            split_state["active_job"] = None
            self._storage.workflow_domain_store.write_split_jobs(project_id, split_state)
            return split_state
        if self._is_live_job(project_id, job_id):
            return split_state
        split_state["active_job"] = None
        split_state["last_error"] = {
            "job_id": job_id,
            "node_id": active_job.get("node_id"),
            "mode": active_job.get("mode"),
            "started_at": active_job.get("started_at"),
            "completed_at": iso_now(),
            "error": _STALE_JOB_MESSAGE,
        }
        return self._storage.workflow_domain_store.write_split_jobs(project_id, split_state)

    def _mark_job_completed(self, project_id: str, job_id: str) -> None:
        try:
            with self._storage.project_lock(project_id):
                split_state = self._storage.workflow_domain_store.read_split_jobs(project_id)
                active_job = split_state.get("active_job")
                if isinstance(active_job, dict) and active_job.get("job_id") == job_id:
                    split_state["active_job"] = None
                    split_state["last_error"] = None
                    split_state["last_completed"] = {
                        "job_id": job_id,
                        "node_id": active_job.get("node_id"),
                        "mode": active_job.get("mode"),
                        "started_at": active_job.get("started_at"),
                        "completed_at": iso_now(),
                    }
                    self._storage.workflow_domain_store.write_split_jobs(project_id, split_state)
        finally:
            self._clear_live_job(project_id, job_id)

    def _mark_job_failed(
        self,
        project_id: str,
        job_id: str,
        node_id: str,
        mode: str,
        started_at: str,
        message: str,
    ) -> None:
        try:
            with self._storage.project_lock(project_id):
                split_state = self._storage.workflow_domain_store.read_split_jobs(project_id)
                active_job = split_state.get("active_job")
                if isinstance(active_job, dict) and active_job.get("job_id") == job_id:
                    split_state["active_job"] = None
                split_state["last_error"] = {
                    "job_id": job_id,
                    "node_id": node_id,
                    "mode": mode,
                    "started_at": started_at,
                    "completed_at": iso_now(),
                    "error": message,
                }
                self._storage.workflow_domain_store.write_split_jobs(project_id, split_state)
        except ProjectNotFound:
            pass
        finally:
            self._clear_live_job(project_id, job_id)

    def _validate_split_eligibility(
        self,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> None:
        if self._is_superseded(node):
            raise SplitNotAllowed("Cannot split a superseded node.")
        if node.get("status") == "done":
            raise SplitNotAllowed("Cannot split a done node.")
        if self._tree_service.active_child_ids(node, node_by_id):
            raise SplitNotAllowed("Cannot split a node that already has child nodes.")
        workflow = self._workflow_summary(snapshot, str(node.get("node_id") or ""))
        if not workflow["frame_confirmed"]:
            raise SplitNotAllowed("Cannot split until the frame is confirmed.")
        if workflow["active_step"] == "clarify":
            raise SplitNotAllowed(
                "Cannot split until the latest confirmed frame has no remaining clarify questions."
            )
        if workflow["active_step"] == "frame":
            raise SplitNotAllowed(
                "Cannot split until the updated frame is re-confirmed and clarify is cleared."
            )

    def _workflow_summary(self, snapshot: dict[str, Any], node_id: str) -> dict[str, Any]:
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if not workspace_root or not node_id:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
            }
        node_dir = planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, node_id)
        if node_dir is None:
            return {
                "frame_confirmed": False,
                "active_step": "frame",
                "spec_confirmed": False,
            }
        return derive_workflow_summary_from_node_dir(node_dir)

    def _extract_split_payload(self, tool_calls: Any, *, stdout: str = "") -> dict[str, Any] | None:
        if not isinstance(tool_calls, list):
            tool_calls = []
        for raw_call in tool_calls:
            if not isinstance(raw_call, dict):
                continue
            if str(raw_call.get("tool_name") or "") != "emit_render_data":
                continue
            arguments = raw_call.get("arguments")
            if not isinstance(arguments, dict):
                continue
            if str(arguments.get("kind") or "") != "split_result":
                continue
            payload = arguments.get("payload")
            if isinstance(payload, dict):
                return deepcopy(payload)
        return self._extract_split_payload_from_stdout(stdout)

    def _extract_split_payload_from_stdout(self, stdout: str) -> dict[str, Any] | None:
        cleaned = str(stdout or "").strip()
        if not cleaned:
            return None
        candidates = [cleaned]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            candidates.append(cleaned[start : end + 1])
        import json
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _bootstrap_split_lineage(
        self,
        project_id: str,
        parent_node_id: str,
        lineage_targets: dict[str, str | None],
    ) -> None:
        del project_id, parent_node_id, lineage_targets

    def _refresh_ask_context(self, project_id: str, node_id: str) -> None:
        self._artifact_turn_runner.refresh_ask_context(
            project_id=project_id,
            node_id=node_id,
            artifact_kind="split",
        )

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _sync_snapshot_tree(self, snapshot: dict[str, Any]) -> None:
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if not workspace_root:
            return
        planningtree_workspace.sync_snapshot_tree(Path(workspace_root), snapshot)

    def _commit_split_projection(
        self,
        *,
        workspace_root: str | None,
        parent_hierarchical_number: str,
        parent_title: str,
    ) -> SplitCommitResult | None:
        if self._git_checkpoint_service is None:
            return None
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return None
        project_path = Path(workspace_root).expanduser().resolve()
        try:
            if not self._git_checkpoint_service.probe_git_initialized(project_path):
                return None
            initial_sha = self._git_checkpoint_service.capture_head_sha(project_path)
            commit_message = self._git_checkpoint_service.build_commit_message(
                parent_hierarchical_number,
                f"split {parent_title}".strip() or "split task",
            )
            committed_sha = self._git_checkpoint_service.commit_if_changed(project_path, commit_message)
            if committed_sha:
                return {
                    "initialSha": initial_sha,
                    "headSha": committed_sha,
                    "commitMessage": commit_message,
                    "committed": True,
                }
            return {
                "initialSha": initial_sha,
                "headSha": initial_sha,
                "commitMessage": commit_message,
                "committed": False,
            }
        except Exception:
            logger.warning(
                "Failed to commit split projection for %s (%s)",
                parent_hierarchical_number,
                parent_title,
                exc_info=True,
            )
            return None

    def _mark_live_job(self, project_id: str, job_id: str) -> None:
        with self._live_jobs_lock:
            self._live_jobs[project_id] = job_id

    def _clear_live_job(self, project_id: str, job_id: str) -> None:
        with self._live_jobs_lock:
            if self._live_jobs.get(project_id) == job_id:
                self._live_jobs.pop(project_id, None)

    def _is_live_job(self, project_id: str, job_id: str) -> bool:
        with self._live_jobs_lock:
            return self._live_jobs.get(project_id) == job_id

    def _is_superseded(self, node: dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))


def _build_flat_subtask_description(subtask: dict[str, str]) -> str:
    return "\n\n".join(
        [
            subtask["objective"].strip(),
            f"Why now: {subtask['why_now'].strip()}",
        ]
    )
