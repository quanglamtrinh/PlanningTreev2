from __future__ import annotations

import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.split_context_builder import build_split_context
from backend.ai.split_prompt_builder import (
    build_hidden_retry_feedback,
    build_split_attempt_prompt,
    build_split_base_instructions,
    split_render_tool,
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
from backend.services.tree_service import TreeService
from backend.split_contract import FlatSubtaskPayload, ServiceSplitMode
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage

_RETRY_LIMIT = 2
_STALE_JOB_MESSAGE = "This split was interrupted because the server restarted before it completed."


class SplitService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        split_timeout: int,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._split_timeout = int(split_timeout)
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}

    def split_node(self, project_id: str, node_id: str, mode: ServiceSplitMode) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(node, node_by_id)
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.split_state_store.read_state(project_id))
            if split_state.get("active_job"):
                raise SplitNotAllowed("A split is already active for this project.")
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            existing_thread_id = split_state.get("thread_id")

        thread_id = self._ensure_project_thread(existing_thread_id, workspace_root)
        job_id = new_id("split")
        started_at = iso_now()

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(node, node_by_id)
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.split_state_store.read_state(project_id))
            if split_state.get("active_job"):
                raise SplitNotAllowed("A split is already active for this project.")
            split_state["thread_id"] = thread_id
            split_state["active_job"] = {
                "job_id": job_id,
                "node_id": node_id,
                "mode": mode,
                "started_at": started_at,
            }
            split_state["last_error"] = None
            self._storage.split_state_store.write_state(project_id, split_state)
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
            split_state = self._reconcile_stale_job_locked(project_id, self._storage.split_state_store.read_state(project_id))
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
            self._materialize_split_payload(project_id, node_id, payload)
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
            split_state = self._storage.split_state_store.read_state(project_id)
            thread_id = str(split_state.get("thread_id") or "").strip()
            if not thread_id:
                raise SplitBackendUnavailable("Split thread is unavailable. Retry the split.")
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            task_context = build_split_context(snapshot, node, node_by_id)

        retry_feedback: str | None = None
        last_issues = ["No valid split_result payload was captured."]
        for attempt in range(_RETRY_LIMIT + 1):
            result = self._codex_client.run_turn_streaming(
                build_split_attempt_prompt(mode, task_context, retry_feedback),
                thread_id=thread_id,
                timeout_sec=self._split_timeout,
                cwd=workspace_root,
            )
            tool_calls = result.get("tool_calls", [])
            payload = self._extract_split_payload(tool_calls)
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
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            parent = node_by_id.get(node_id)
            if parent is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(parent, node_by_id)

            now = iso_now()
            inherited_locked = parent.get("status") == "locked" or self._tree_service.has_locked_ancestor(parent, node_by_id)
            parent_hnum = str(parent.get("hierarchical_number") or "1")
            created_child_ids: list[str] = []
            for index, subtask in enumerate(payload["subtasks"], start=1):
                child_id = uuid4().hex
                child_node = {
                    "node_id": child_id,
                    "parent_id": node_id,
                    "child_ids": [],
                    "title": subtask["title"],
                    "description": _build_flat_subtask_description(subtask),
                    "status": "locked" if inherited_locked or index != 1 else "ready",
                    "node_kind": "original",
                    "depth": int(parent.get("depth", 0) or 0) + 1,
                    "display_order": index - 1,
                    "hierarchical_number": f"{parent_hnum}.{index}",
                    "created_at": now,
                }
                parent.setdefault("child_ids", []).append(child_id)
                snapshot["tree_state"]["node_index"][child_id] = child_node
                node_by_id[child_id] = child_node
                created_child_ids.append(child_id)

            if not created_child_ids:
                raise SplitInvalidResponse(["payload.subtasks must contain at least one item"])

            if parent.get("status") in {"ready", "in_progress"}:
                parent["status"] = "draft"

            snapshot["tree_state"]["active_node_id"] = created_child_ids[0]
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            snapshot["project"] = self._storage.project_store.touch_meta(project_id, now)
            self._sync_snapshot_tree(snapshot)

    def _ensure_project_thread(self, existing_thread_id: Any, workspace_root: str | None) -> str:
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            try:
                self._codex_client.resume_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    timeout_sec=15,
                )
                return existing_thread_id.strip()
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise SplitBackendUnavailable(str(exc)) from exc

        try:
            response = self._codex_client.start_thread(
                base_instructions=build_split_base_instructions(),
                dynamic_tools=[split_render_tool()],
                cwd=workspace_root,
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            raise SplitBackendUnavailable(str(exc)) from exc

        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise SplitBackendUnavailable("Split thread start did not return a thread id.")
        return thread_id

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
            self._storage.split_state_store.write_state(project_id, split_state)
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
        return self._storage.split_state_store.write_state(project_id, split_state)

    def _mark_job_completed(self, project_id: str, job_id: str) -> None:
        try:
            with self._storage.project_lock(project_id):
                split_state = self._storage.split_state_store.read_state(project_id)
                active_job = split_state.get("active_job")
                if isinstance(active_job, dict) and active_job.get("job_id") == job_id:
                    split_state["active_job"] = None
                    split_state["last_error"] = None
                    self._storage.split_state_store.write_state(project_id, split_state)
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
                split_state = self._storage.split_state_store.read_state(project_id)
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
                self._storage.split_state_store.write_state(project_id, split_state)
        except ProjectNotFound:
            pass
        finally:
            self._clear_live_job(project_id, job_id)

    def _validate_split_eligibility(
        self,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> None:
        if self._is_superseded(node):
            raise SplitNotAllowed("Cannot split a superseded node.")
        if node.get("status") == "done":
            raise SplitNotAllowed("Cannot split a done node.")
        if self._tree_service.active_child_ids(node, node_by_id):
            raise SplitNotAllowed("Cannot split a node that already has child nodes.")

    def _extract_split_payload(self, tool_calls: Any) -> dict[str, Any] | None:
        if not isinstance(tool_calls, list):
            return None
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
        return None

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

    def _is_missing_thread_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message

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
