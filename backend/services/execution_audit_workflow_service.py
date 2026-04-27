from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from backend.ai.codex_client import CodexTransportError
from backend.business.workflow_v2.execution_audit_helpers import WorkspaceCommitResult
from backend.business.workflow_v2.errors import WorkflowActionNotAllowedError, WorkflowV2Error
from backend.conversation.projector.thread_event_projector import upsert_item as upsert_item_v2
from backend.conversation.projector.thread_event_projector_runtime_v3 import upsert_item_v3
from backend.conversation.services.thread_runtime_service_v3 import ThreadRuntimeServiceV3
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.errors.app_errors import (
    AuditLineageUnavailable,
    FinishTaskNotAllowed,
    NodeNotFound,
    ReviewNotAllowed,
)
from backend.services.execution_file_change_hydrator import (
    ExecutionFileChangeDiffSource,
    ExecutionFileChangeHydrator,
)
from backend.services.finish_task_service import FinishTaskService
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.review_service import ReviewService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_text, iso_now, load_text, new_id
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

_HANDOFF_SUMMARY_PLACEHOLDER = "No execution summary."
_HANDOFF_DOCS_DIR = "docs"
_HANDOFF_FILE_NAME = "handoff.md"
_HANDOFF_FILE_HEADER = "# PlanningTree Handoff\n\n"
_LIVE_FILE_CHANGE_HYDRATE_DEBOUNCE_SEC = 0.35
_HANDOFF_NODE_BLOCK_RE = re.compile(
    r"<!-- PT_HANDOFF_NODE:(?P<node_id>[^>\r\n]+) -->\n(?P<body>.*?)\n<!-- /PT_HANDOFF_NODE:(?P=node_id) -->\n?",
    re.DOTALL,
)


class WorkflowDecisionService:
    def build_view(self, state: dict[str, Any]) -> dict[str, Any]:
        phase = str(state.get("workflowPhase") or "idle")
        current_execution_decision = copy.deepcopy(state.get("currentExecutionDecision"))
        current_audit_decision = copy.deepcopy(state.get("currentAuditDecision"))
        return {
            "nodeId": state.get("nodeId"),
            "workflowPhase": phase,
            "askThreadId": state.get("askThreadId"),
            "executionThreadId": state.get("executionThreadId"),
            "auditLineageThreadId": state.get("auditLineageThreadId"),
            "reviewThreadId": state.get("reviewThreadId"),
            "activeExecutionRunId": state.get("activeExecutionRunId"),
            "latestExecutionRunId": state.get("latestExecutionRunId"),
            "activeReviewCycleId": state.get("activeReviewCycleId"),
            "latestReviewCycleId": state.get("latestReviewCycleId"),
            "currentExecutionDecision": current_execution_decision,
            "currentAuditDecision": current_audit_decision,
            "acceptedSha": state.get("acceptedSha"),
            "runtimeBlock": copy.deepcopy(state.get("runtimeBlock")),
            "canSendExecutionMessage": phase == "execution_decision_pending" and current_execution_decision is not None,
            "canReviewInAudit": phase == "execution_decision_pending" and current_execution_decision is not None,
            "canImproveInExecution": phase == "audit_decision_pending" and current_audit_decision is not None,
            "canMarkDoneFromExecution": phase == "execution_decision_pending" and current_execution_decision is not None,
            "canMarkDoneFromAudit": phase == "audit_decision_pending" and current_audit_decision is not None,
        }


class WorkflowMetadataService:
    def __init__(self, tree_service: TreeService, finish_task_service: FinishTaskService) -> None:
        self._tree_service = tree_service
        self._finish_task_service = finish_task_service

    def load_execution_metadata(
        self,
        project_id: str,
        node_id: str,
        *,
        validate_finish_task: bool = False,
    ) -> dict[str, Any]:
        snapshot = self._finish_task_service._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        node_dir = self._finish_task_service._resolve_node_dir(snapshot, node_id)
        if validate_finish_task:
            spec_content = self._finish_task_service._validate_finish_task_locked(
                project_id,
                node_id,
                snapshot,
                node,
                node_dir,
            )
        else:
            spec_path = node_dir / "spec.md"
            spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
            if not spec_content.strip():
                raise FinishTaskNotAllowed("Spec must be non-empty before execution can run.")
        return {
            "snapshot": snapshot,
            "node": node,
            "nodeById": node_by_id,
            "specContent": spec_content,
            "frameContent": self._finish_task_service._load_confirmed_frame_content(node_dir),
            "taskContext": build_split_context(snapshot, node, node_by_id),
            "workspaceRoot": self._finish_task_service._workspace_root_from_snapshot(snapshot),
            "initialSha": self._finish_task_service._compute_initial_sha(project_id, node_id, snapshot),
        }

    @staticmethod
    def build_execution_start_prompt() -> str:
        return (
            "Implement the confirmed task in this workspace now.\n"
            "The complete task context has already been injected into this execution thread.\n"
            "Do not ask clarifying questions.\n"
            "Make concrete changes, verify results, and then summarize what changed."
        )

    @staticmethod
    def build_execution_followup_prompt(
        *,
        spec_content: str,
        frame_content: str,
        task_context: dict[str, Any],
        instruction_text: str,
    ) -> str:
        del spec_content, frame_content, task_context
        follow_up = (
            "Execution follow-up request:\n"
            "```text\n"
            f"{instruction_text.strip()}\n"
            "```\n\n"
            "Apply this follow-up incrementally on top of the current workspace. "
            "Do not ask for clarification. Keep working toward the same confirmed task."
        )
        return f"{base}\n\n{follow_up}"

    @staticmethod
    def build_improve_prompt(
        *,
        spec_content: str,
        frame_content: str,
        task_context: dict[str, Any],
        review_text: str,
    ) -> str:
        del spec_content, frame_content, task_context
        improve = (
            "The execution/audit context is already available in this thread.\n"
            "Apply the review feedback below directly in the workspace.\n\n"
            "Latest local review feedback:\n"
            "```markdown\n"
            f"{review_text.strip()}\n"
            "```\n\n"
            "Improve the implementation to address this review feedback now. "
            "Keep the solution aligned with the confirmed task and existing codebase."
        )
        return improve

    @staticmethod
    def _truncate_for_prompt(text: str, *, char_limit: int) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        if len(normalized) <= char_limit:
            return normalized
        if char_limit <= 3:
            return normalized[:char_limit]
        return normalized[: char_limit - 3].rstrip() + "..."

    @classmethod
    def build_audit_review_prompt(
        cls,
        *,
        node: dict[str, Any],
        spec_content: str,
        frame_content: str,
        review_commit_sha: str,
    ) -> str:
        del spec_content, frame_content
        task_number = str(node.get("hierarchical_number") or "").strip()
        task_title = str(node.get("title") or "").strip() or "Task"
        task_label = f"{task_number} {task_title}".strip()

        sections = [
            "You are reviewing code changes that were just completed in the current workspace.\n",
            "The complete task context has already been injected into this audit thread.\n\n",
            "I just completed code for task:\n",
            f"- {task_label}\n\n",
            f"The commit hash is `{review_commit_sha}`.\n",
            "Please review this implementation.\n",
            "Do you have any questions or issues?\n\n",
            "Review requirements:\n",
            "1. Evaluate strictly against the confirmed spec/frame already present in thread context.\n",
            "2. Prioritize bugs, regressions, missing tests, and maintainability risks.\n",
            "3. Ignore changes under `.planningtree/`.\n",
            "4. If there are no serious issues, state that explicitly.\n",
            "5. Include concrete file paths for findings whenever possible.\n",
            f"6. Start by inspecting commit `{review_commit_sha}` and its related diffs.\n",
            "7. Respond in plain markdown prose for humans.\n",
            "8. Do NOT return JSON/YAML objects or fenced data payloads.\n",
        ]
        return "".join(sections)


class GitArtifactService:
    def __init__(self, git_checkpoint_service: GitCheckpointService | None) -> None:
        self._git_checkpoint_service = git_checkpoint_service

    @staticmethod
    def _is_planningtree_relative_path(path: str | None) -> bool:
        candidate = str(path or "").replace("\\", "/").strip().lower()
        if not candidate:
            return False
        if len(candidate) >= 2 and candidate[1] == ":":
            candidate = candidate[2:]
        candidate = candidate.lstrip("/")
        candidate = re.sub(r"^\./+", "", candidate)
        return candidate == ".planningtree" or candidate.startswith(".planningtree/")

    def compute_workspace_hash(self, workspace_root: str | None) -> str:
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        return compute_workspace_sha(Path(workspace_root).expanduser().resolve())

    def require_workspace_hash(self, workspace_root: str | None, expected_workspace_hash: str) -> str:
        actual = self.compute_workspace_hash(workspace_root)
        if actual != expected_workspace_hash:
            raise FinishTaskNotAllowed(
                f"Workspace drift detected. Expected workspace hash {expected_workspace_hash}, got {actual}."
            )
        return actual

    def require_head_sha(self, workspace_root: str | None, expected_head_sha: str) -> str:
        if self._git_checkpoint_service is None:
            raise ReviewNotAllowed("Git-backed review acceptance is unavailable.")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise ReviewNotAllowed("Project snapshot is missing project_path.")
        actual = self._git_checkpoint_service.capture_head_sha(Path(workspace_root).expanduser().resolve())
        if actual != expected_head_sha:
            raise ReviewNotAllowed(
                f"Workspace HEAD drift detected. Expected {expected_head_sha}, got {actual}."
            )
        return actual

    def commit_workspace(
        self,
        *,
        workspace_root: str | None,
        hierarchical_number: str,
        title: str,
        verb: str,
    ) -> WorkspaceCommitResult:
        if self._git_checkpoint_service is None:
            raise FinishTaskNotAllowed("Git checkpoint service is unavailable.")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(workspace_root).expanduser().resolve()
        initial_sha = self._git_checkpoint_service.capture_head_sha(project_path)
        commit_message = self._git_checkpoint_service.build_commit_message(
            hierarchical_number,
            f"{verb} {title}".strip(),
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

    def get_worktree_diff(
        self,
        *,
        workspace_root: str | None,
        start_sha: str | None,
        paths: list[str] | None = None,
    ) -> str:
        if self._git_checkpoint_service is None:
            return ""
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return ""
        if not isinstance(start_sha, str) or not start_sha.strip():
            return ""

        project_path = Path(workspace_root).expanduser().resolve()
        normalized_paths: list[str] = []
        for raw_path in paths or []:
            candidate = str(raw_path or "").strip()
            if not candidate:
                continue
            path_obj = Path(candidate)
            if path_obj.is_absolute():
                try:
                    rel = path_obj.expanduser().resolve().relative_to(project_path)
                    normalized_rel = rel.as_posix()
                    if self._is_planningtree_relative_path(normalized_rel):
                        continue
                    normalized_paths.append(normalized_rel)
                    continue
                except Exception:
                    pass
            normalized_path = candidate
            if self._is_planningtree_relative_path(normalized_path):
                continue
            normalized_paths.append(normalized_path)

        try:
            if normalized_paths and hasattr(self._git_checkpoint_service, "get_worktree_diff_against_sha_for_paths"):
                return str(
                    self._git_checkpoint_service.get_worktree_diff_against_sha_for_paths(
                        project_path,
                        start_sha,
                        normalized_paths,
                    )
                    or ""
                )
            if hasattr(self._git_checkpoint_service, "get_worktree_diff_against_sha"):
                return str(
                    self._git_checkpoint_service.get_worktree_diff_against_sha(
                        project_path,
                        start_sha,
                    )
                    or ""
                )
        except Exception:
            logger.debug(
                "Failed to collect worktree diff for %s from %s",
                str(project_path),
                start_sha,
                exc_info=True,
            )
        return ""


class ExecutionAuditWorkflowService:
    def __init__(
        self,
        *,
        storage: Storage,
        tree_service: TreeService,
        finish_task_service: FinishTaskService,
        review_service: ReviewService,
        thread_runtime_service: ThreadRuntimeServiceV3,
        thread_query_service: Any | None = None,
        workflow_event_publisher: WorkflowEventPublisher,
        git_checkpoint_service: GitCheckpointService | None,
        codex_client: Any,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._finish_task_service = finish_task_service
        self._review_service = review_service
        self._thread_runtime_service = thread_runtime_service
        # Compatibility alias for older tests/helpers that still set/read
        # `_thread_runtime_service_v2` on object.__new__-constructed instances.
        self._thread_runtime_service_v2 = thread_runtime_service
        self._thread_query_service = (
            thread_query_service
            if thread_query_service is not None
            else getattr(thread_runtime_service, "_query_service", None)
        )
        self._workflow_event_publisher = workflow_event_publisher
        self._codex_client = codex_client
        self._decision_service = WorkflowDecisionService()
        self._metadata_service = WorkflowMetadataService(tree_service, finish_task_service)
        self._artifact_service = GitArtifactService(git_checkpoint_service)
        self._workflow_orchestrator_v2: Any | None = None

    def _resolve_workflow_orchestrator_v2(self) -> Any | None:
        return getattr(self, "_workflow_orchestrator_v2", None)

    def _require_workflow_orchestrator_v2(self) -> Any:
        orchestrator = self._resolve_workflow_orchestrator_v2()
        if orchestrator is None:
            raise WorkflowV2Error(
                "ERR_WORKFLOW_V2_ORCHESTRATOR_UNAVAILABLE",
                "Execution/audit workflow actions require Workflow Core V2.",
                status_code=503,
                details={"surface": "execution_audit_workflow_service"},
            )
        return orchestrator

    def _resolve_thread_query_service(self) -> Any | None:
        query_service = getattr(self, "_thread_query_service", None)
        if query_service is not None:
            return query_service
        runtime_service = self._resolve_thread_runtime_service()
        if runtime_service is None:
            return None
        return getattr(runtime_service, "_query_service", None)

    def _resolve_thread_runtime_service(self) -> Any | None:
        runtime_service = getattr(self, "_thread_runtime_service", None)
        if runtime_service is not None:
            return runtime_service
        return getattr(self, "_thread_runtime_service_v2", None)

    def _is_query_service_v3(self) -> bool:
        query_service = self._resolve_thread_query_service()
        if query_service is None:
            return False
        if hasattr(query_service, "_snapshot_store_v3"):
            return True
        return "v3" in type(query_service).__name__.lower()

    def _get_thread_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        *,
        publish_repairs: bool = True,
        ensure_binding: bool = True,
        allow_thread_read_hydration: bool | None = None,
    ) -> dict[str, Any]:
        query_service = self._resolve_thread_query_service()
        if query_service is None:
            raise FinishTaskNotAllowed("Thread query service unavailable.")
        kwargs: dict[str, Any] = {
            "publish_repairs": publish_repairs,
            "ensure_binding": ensure_binding,
        }
        if allow_thread_read_hydration is not None:
            kwargs["allow_thread_read_hydration"] = allow_thread_read_hydration
        try:
            return query_service.get_thread_snapshot(project_id, node_id, thread_role, **kwargs)
        except TypeError:
            kwargs.pop("allow_thread_read_hydration", None)
            return query_service.get_thread_snapshot(project_id, node_id, thread_role, **kwargs)

    def _build_stream_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        *,
        after_snapshot_version: int | None,
    ) -> dict[str, Any]:
        query_service = self._resolve_thread_query_service()
        if query_service is None:
            raise FinishTaskNotAllowed("Thread query service unavailable.")
        return query_service.build_stream_snapshot(
            project_id,
            node_id,
            thread_role,
            after_snapshot_version=after_snapshot_version,
            ensure_binding=False,
        )

    def _persist_thread_mutation(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        query_service = self._resolve_thread_query_service()
        if query_service is None:
            raise FinishTaskNotAllowed("Thread query service unavailable.")
        query_service.persist_thread_mutation(project_id, node_id, thread_role, snapshot, events)

    def _upsert_item(
        self,
        snapshot: dict[str, Any],
        item: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if self._is_query_service_v3():
            return upsert_item_v3(snapshot, item)
        return upsert_item_v2(snapshot, item)

    def get_workflow_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        view = orchestrator.get_legacy_workflow_state(project_id, node_id)
        view["askThreadId"] = self._resolve_ask_thread_id(project_id, node_id)
        execution_entry = self._storage.thread_registry_store.read_entry(project_id, node_id, "execution")
        audit_entry = self._storage.thread_registry_store.read_entry(project_id, node_id, "audit")
        if not view.get("executionThreadId"):
            view["executionThreadId"] = str(execution_entry.get("threadId") or "").strip() or None
        if not view.get("auditLineageThreadId"):
            view["auditLineageThreadId"] = str(audit_entry.get("threadId") or "").strip() or None
        if not view.get("reviewThreadId"):
            view["reviewThreadId"] = str(audit_entry.get("threadId") or "").strip() or None
        return view

    def finish_task(self, project_id: str, node_id: str, *, idempotency_key: str) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        refresh_reason = "finish_task_started"
        try:
            response = orchestrator.start_execution(
                project_id,
                node_id,
                idempotency_key=idempotency_key,
            )
        except WorkflowActionNotAllowedError as exc:
            if exc.details.get("action") != "start_execution" or exc.details.get("phase") != "executing":
                raise
            active_response = orchestrator.get_active_execution_start_response(project_id, node_id)
            if active_response is None:
                raise
            response = active_response
            refresh_reason = "finish_task_already_executing"
        state = orchestrator.get_legacy_workflow_state(project_id, node_id)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason=refresh_reason)
        return {
            "accepted": True,
            "threadId": response.get("threadId"),
            "turnId": response.get("turnId"),
            "executionRunId": response.get("executionRunId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def start_execution_followup(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        text: str,
    ) -> dict[str, Any]:
        del project_id, node_id, idempotency_key, text
        raise WorkflowV2Error(
            "ERR_WORKFLOW_V3_EXECUTION_FOLLOWUP_DEPRECATED",
            "V3 execution follow-up turns are deprecated. Use Session Core V2.",
            status_code=410,
            details={"surface": "workflow-v3", "replacement": "session-v2"},
        )

    def resolve_thread_route(self, project_id: str, node_id: str, thread_id: str) -> str:
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("executionThreadId") or "") == thread_id:
                return "execution"
            if str(state.get("reviewThreadId") or "") == thread_id:
                return "audit"
            raise FinishTaskNotAllowed(f"Thread {thread_id!r} is not active for node {node_id!r}.")

    def get_thread_snapshot_by_id(self, project_id: str, node_id: str, thread_id: str) -> dict[str, Any]:
        thread_role = self.resolve_thread_route(project_id, node_id, thread_id)
        return self._get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
        )

    def build_stream_snapshot_by_id(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        *,
        after_snapshot_version: int | None,
    ) -> tuple[str, dict[str, Any]]:
        thread_role = self.resolve_thread_route(project_id, node_id, thread_id)
        snapshot = self._build_stream_snapshot(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            after_snapshot_version=after_snapshot_version,
        )
        return thread_role, snapshot

    def mark_done_from_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        orchestrator.mark_done_from_execution(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_workspace_hash=expected_workspace_hash,
        )
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="mark_done_from_execution")
        return orchestrator.get_legacy_workflow_state(project_id, node_id)

    def improve_in_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        response = orchestrator.request_improvements(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_review_commit_sha=expected_review_commit_sha,
        )
        state = orchestrator.get_legacy_workflow_state(project_id, node_id)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="improve_in_execution_started")
        return {
            "accepted": True,
            "threadId": response.get("threadId"),
            "turnId": response.get("turnId"),
            "executionRunId": response.get("executionRunId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def _start_execution_run(
        self,
        *,
        project_id: str,
        node_id: str,
        idempotency_key: str,
        prompt: str,
        start_sha: str,
        trigger_kind: str,
        source_review_cycle_id: str | None,
        workspace_root: str | None,
        summary_seed: str | None,
        local_user_text: str | None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            allowed_phases = {"idle", "execution_decision_pending", "audit_decision_pending"}
            if str(state.get("workflowPhase") or "") not in allowed_phases:
                raise FinishTaskNotAllowed(
                    "Execution can only start from idle, execution_decision_pending, or audit_decision_pending."
                )
            resolved_execution_thread_id = str(state.get("executionThreadId") or "").strip()
            if not resolved_execution_thread_id:
                resolved_execution_thread_id = self._finish_task_service._ensure_execution_thread_id_v2(
                    project_id,
                    node_id,
                    workspace_root,
                )
                state["executionThreadId"] = resolved_execution_thread_id
            snapshot = self._get_thread_snapshot(
                project_id,
                node_id,
                "execution",
                publish_repairs=False,
                ensure_binding=False,
            )
            turn_id = new_id("exec")
            created_items: list[dict[str, Any]] = []
            if local_user_text:
                created_items.append(
                    self._build_local_user_item(
                        snapshot=snapshot,
                        thread_id=resolved_execution_thread_id,
                        turn_id=turn_id,
                        text=local_user_text,
                    )
                )
            self._resolve_thread_runtime_service().begin_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                origin=f"workflow_{trigger_kind}",
                created_items=created_items,
                turn_id=turn_id,
            )
            run_id = new_id("exec_run")
            run = {
                "runId": run_id,
                "projectId": project_id,
                "nodeId": node_id,
                "executionThreadId": resolved_execution_thread_id,
                "executionTurnId": turn_id,
                "clientRequestId": idempotency_key,
                "triggerKind": trigger_kind,
                "sourceReviewCycleId": source_review_cycle_id,
                "startSha": start_sha,
                "candidateWorkspaceHash": None,
                "committedHeadSha": None,
                "status": "running",
                "decision": "pending",
                "summaryText": summary_seed,
                "errorMessage": None,
                "startedAt": iso_now(),
                "completedAt": None,
                "decidedAt": None,
            }
            self._storage.execution_run_store.append_run(project_id, node_id, run)
            state["workflowPhase"] = "execution_running"
            state["activeExecutionRunId"] = run_id
            state["latestExecutionRunId"] = run_id
            if trigger_kind == "improve_from_review":
                state["currentAuditDecision"] = None
            state["currentExecutionDecision"] = None
            self._storage.workflow_state_store.write_state(project_id, node_id, state)

        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason=f"{trigger_kind}_started")
        threading.Thread(
            target=self._run_execution_background,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "run_id": run_id,
                "turn_id": turn_id,
                "thread_id": resolved_execution_thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
                "start_sha": start_sha,
            },
            daemon=True,
        ).start()
        return {
            "accepted": True,
            "threadId": resolved_execution_thread_id,
            "turnId": turn_id,
            "executionRunId": run_id,
            "workflowPhase": "execution_running",
        }

    def _run_execution_background(
        self,
        *,
        project_id: str,
        node_id: str,
        run_id: str,
        turn_id: str,
        thread_id: str,
        prompt: str,
        workspace_root: str | None,
        start_sha: str,
    ) -> None:
        turn_finalized = False
        try:
            last_live_file_change_hydrate_at = 0.0

            def handle_live_file_change_hydration(raw_event: dict[str, Any]) -> None:
                nonlocal last_live_file_change_hydrate_at
                if not self._should_trigger_live_file_change_hydrate(raw_event):
                    return
                method = str(raw_event.get("method") or "").strip()
                now_mono = time.monotonic()
                if (
                    method != "turn/completed"
                    and now_mono - last_live_file_change_hydrate_at < _LIVE_FILE_CHANGE_HYDRATE_DEBOUNCE_SEC
                ):
                    return
                last_live_file_change_hydrate_at = now_mono
                self._hydrate_execution_file_change_diff_from_worktree(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    workspace_root=workspace_root,
                    start_sha=start_sha,
                    hydrated_by="execution_audit_worktree_live",
                    refresh_synthetic_from_full_diff=True,
                )

            stream_result = self._resolve_thread_runtime_service().stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                thread_id=thread_id,
                turn_id=turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                timeout_sec=self._finish_task_service._chat_timeout,
                on_raw_event_applied=handle_live_file_change_hydration,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._resolve_thread_runtime_service().outcome_from_turn_status(turn_status)
            if outcome != "completed":
                raise FinishTaskNotAllowed(
                    f"Execution run returned unsupported terminal status {turn_status or 'unknown'}."
                )
            self._hydrate_execution_file_change_diff_from_worktree(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                workspace_root=workspace_root,
                start_sha=start_sha,
                refresh_synthetic_from_full_diff=True,
            )
            self._resolve_thread_runtime_service().complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                outcome="completed",
            )
            turn_finalized = True
            summary_text = str(result.get("stdout") or "").strip() or None
            candidate_workspace_hash = self._artifact_service.compute_workspace_hash(workspace_root)
            with self._storage.project_lock(project_id):
                runs = self._storage.execution_run_store.read_runs(project_id, node_id)
                for run in runs:
                    if str(run.get("runId") or "") != run_id:
                        continue
                    run["status"] = "completed"
                    run["candidateWorkspaceHash"] = candidate_workspace_hash
                    run["summaryText"] = summary_text
                    run["completedAt"] = iso_now()
                    break
                self._storage.execution_run_store.write_runs(project_id, node_id, runs)
                state = self._ensure_workflow_state_locked(project_id, node_id)
                state["workflowPhase"] = "execution_decision_pending"
                state["activeExecutionRunId"] = None
                state["latestExecutionRunId"] = run_id
                state["currentExecutionDecision"] = self._materialize_execution_decision(
                    run_id=run_id,
                    turn_id=turn_id,
                    candidate_workspace_hash=candidate_workspace_hash,
                    summary_text=summary_text,
                )
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
        except Exception as exc:
            logger.exception("Execution workflow run failed for %s/%s", project_id, node_id, exc_info=exc)
            if not turn_finalized:
                try:
                    error_item = self._resolve_thread_runtime_service().build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        thread_id=thread_id,
                        message=str(exc),
                    )
                    self._resolve_thread_runtime_service().complete_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        outcome="failed",
                        error_item=error_item,
                    )
                except Exception:
                    logger.debug("Failed to finalize execution turn %s/%s", project_id, node_id, exc_info=True)
            with self._storage.project_lock(project_id):
                runs = self._storage.execution_run_store.read_runs(project_id, node_id)
                for run in runs:
                    if str(run.get("runId") or "") != run_id:
                        continue
                    run["status"] = "failed"
                    run["errorMessage"] = str(exc)
                    run["completedAt"] = iso_now()
                    break
                self._storage.execution_run_store.write_runs(project_id, node_id, runs)
                state = self._ensure_workflow_state_locked(project_id, node_id)
                state["workflowPhase"] = "failed"
                state["activeExecutionRunId"] = None
                state["runtimeBlock"] = {"kind": "execution_failed", "message": str(exc)}
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
        finally:
            self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="execution_run_settled")

    @staticmethod
    def _looks_like_structured_diff(text: str | None) -> bool:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return False
        return (
            "diff --git " in normalized
            or "*** Begin Patch" in normalized
            or "\n@@ " in f"\n{normalized}"
            or "\n+++ " in f"\n{normalized}"
            or "\n--- " in f"\n{normalized}"
        )

    @staticmethod
    def _normalize_path_for_diff_match(path: str | None) -> str:
        candidate = str(path or "").replace("\\", "/").strip()
        if not candidate:
            return ""
        if len(candidate) >= 2 and candidate[1] == ":":
            candidate = candidate[2:]
        candidate = candidate.lstrip("/")
        candidate = re.sub(r"^\./+", "", candidate)
        return candidate.lower()

    @staticmethod
    def _is_planningtree_path(path: str | None) -> bool:
        normalized = ExecutionAuditWorkflowService._normalize_path_for_diff_match(path)
        return normalized == ".planningtree" or normalized.startswith(".planningtree/")

    @staticmethod
    def _strip_git_ab_prefix(path: str) -> str:
        candidate = str(path or "").strip().replace("\\", "/")
        if candidate.startswith(("a/", "b/")) and len(candidate) > 2:
            return candidate[2:]
        return candidate

    @staticmethod
    def _extract_paths_from_diff_git_header(line: str) -> list[str]:
        payload = line[len("diff --git ") :].strip()
        if not payload:
            return []
        paths: list[str] = []
        rest = payload
        while rest:
            if rest.startswith('"'):
                end = rest.find('"', 1)
                if end < 0:
                    break
                token = rest[1:end]
                rest = rest[end + 1 :].lstrip()
            else:
                space = rest.find(" ")
                token = rest if space < 0 else rest[:space]
                rest = "" if space < 0 else rest[space + 1 :].lstrip()
            normalized = ExecutionAuditWorkflowService._strip_git_ab_prefix(token)
            if normalized:
                paths.append(normalized)
        return paths

    @staticmethod
    def _parse_unified_diff_blocks(diff_text: str) -> list[dict[str, Any]]:
        normalized = str(diff_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return []
        lines = normalized.split("\n")
        starts: list[tuple[int, list[str]]] = []
        for index, line in enumerate(lines):
            if line.startswith("diff --git "):
                paths = ExecutionAuditWorkflowService._extract_paths_from_diff_git_header(line)
                starts.append((index, paths))
        if not starts:
            return [{"paths": [], "text": normalized.strip()}]
        blocks: list[dict[str, Any]] = []
        for idx, (start, paths) in enumerate(starts):
            end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
            block_text = "\n".join(lines[start:end]).strip()
            if not block_text:
                continue
            blocks.append({"paths": paths, "text": block_text})
        return blocks

    @staticmethod
    def _normalize_change_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_type_to_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"created", "create", "add"}:
            return "add"
        if normalized in {"deleted", "delete", "remove", "removed"}:
            return "delete"
        if normalized in {"updated", "update", "modify", "modified", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_kind_to_change_type(kind: str) -> str:
        if kind == "add":
            return "created"
        if kind == "delete":
            return "deleted"
        return "updated"

    @staticmethod
    def _extract_file_change_changes(item: dict[str, Any]) -> list[dict[str, Any]]:
        raw_changes = item.get("changes") if isinstance(item.get("changes"), list) else None
        rows = (
            raw_changes
            if raw_changes is not None
            else item.get("outputFiles")
            if isinstance(item.get("outputFiles"), list)
            else []
        )
        extracted: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if not path:
                continue
            if ExecutionAuditWorkflowService._is_planningtree_path(path):
                continue
            kind = ExecutionAuditWorkflowService._normalize_change_kind(
                raw.get("kind"),
                fallback=ExecutionAuditWorkflowService._change_type_to_kind(raw.get("changeType"), fallback="modify"),
            )
            diff_value = raw.get("diff")
            if not isinstance(diff_value, str):
                diff_value = raw.get("patchText")
            diff_text = str(diff_value or "").strip() or None
            summary_value = raw.get("summary")
            summary = str(summary_value).strip() if isinstance(summary_value, str) and str(summary_value).strip() else None
            extracted.append(
                {
                    "path": path,
                    "kind": kind,
                    "diff": diff_text,
                    "summary": summary,
                }
            )
        return extracted

    @staticmethod
    def _output_files_from_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for change in changes:
            path = str(change.get("path") or "").strip()
            if not path:
                continue
            if ExecutionAuditWorkflowService._is_planningtree_path(path):
                continue
            kind = ExecutionAuditWorkflowService._normalize_change_kind(change.get("kind"), fallback="modify")
            file_entry: dict[str, Any] = {
                "path": path,
                "changeType": ExecutionAuditWorkflowService._change_kind_to_change_type(kind),
                "summary": str(change.get("summary")).strip() if isinstance(change.get("summary"), str) and str(change.get("summary")).strip() else None,
                "kind": kind,
            }
            diff_text = str(change.get("diff") or "").strip()
            if diff_text:
                file_entry["diff"] = diff_text
            files.append(file_entry)
        return files

    @staticmethod
    def _score_paths_for_match(candidate_paths: list[str], target_path: str) -> int:
        if not target_path:
            return 0
        target_base = Path(target_path).name.lower()
        best = 0
        for candidate in candidate_paths:
            normalized = ExecutionAuditWorkflowService._normalize_path_for_diff_match(candidate)
            if not normalized:
                continue
            if normalized == target_path:
                return 10000 + len(normalized)
            if target_path.endswith(f"/{normalized}") or normalized.endswith(f"/{target_path}"):
                best = max(best, 5000 + min(len(normalized), len(target_path)))
                continue
            if normalized.endswith(target_base) and target_base:
                best = max(best, 500 + len(normalized))
        return best

    @staticmethod
    def _resolve_diff_block_for_path(
        blocks: list[dict[str, Any]],
        *,
        path: str,
        file_index: int,
    ) -> dict[str, Any] | None:
        normalized_target = ExecutionAuditWorkflowService._normalize_path_for_diff_match(path)
        best_index = -1
        best_score = 0
        for idx, block in enumerate(blocks):
            block_paths = block.get("paths")
            if not isinstance(block_paths, list):
                continue
            score = ExecutionAuditWorkflowService._score_paths_for_match(block_paths, normalized_target)
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index >= 0 and best_score >= 500:
            return blocks[best_index]
        if 0 <= file_index < len(blocks):
            return blocks[file_index]
        if len(blocks) == 1:
            return blocks[0]
        return None

    @staticmethod
    def _primary_path_from_block_paths(paths: list[str] | None) -> str:
        if not isinstance(paths, list):
            return ""
        for candidate in reversed(paths):
            normalized = ExecutionAuditWorkflowService._normalize_path_for_diff_match(candidate)
            if normalized and normalized != "dev/null":
                return str(candidate)
        for candidate in reversed(paths):
            raw = str(candidate or "").strip()
            if raw:
                return raw
        return ""

    @staticmethod
    def _change_kind_from_diff_block_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if (
            re.search(r"(?m)^new file mode\b", normalized)
            or re.search(r"(?m)^--- /dev/null$", normalized)
        ):
            return "add"
        if (
            re.search(r"(?m)^deleted file mode\b", normalized)
            or re.search(r"(?m)^\+\+\+ /dev/null$", normalized)
        ):
            return "delete"
        return "modify"

    @staticmethod
    def _changes_from_diff_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not blocks:
            return []
        changes: list[dict[str, Any]] = []
        seen = set()
        for block in blocks:
            block_paths = block.get("paths")
            path = ExecutionAuditWorkflowService._primary_path_from_block_paths(
                block_paths if isinstance(block_paths, list) else None
            )
            normalized_path = ExecutionAuditWorkflowService._normalize_path_for_diff_match(path)
            if (
                not normalized_path
                or normalized_path == "dev/null"
                or normalized_path in seen
                or ExecutionAuditWorkflowService._is_planningtree_path(path)
            ):
                continue
            text = str(block.get("text") or "").strip()
            changes.append(
                {
                    "path": path,
                    "kind": ExecutionAuditWorkflowService._change_kind_from_diff_block_text(text),
                    "diff": text or None,
                    "summary": "Hydrated from git diff",
                }
            )
            seen.add(normalized_path)
        return changes

    @staticmethod
    def _file_change_item_has_planningtree_paths(item: dict[str, Any]) -> bool:
        rows: list[Any] = []
        raw_changes = item.get("changes")
        raw_output_files = item.get("outputFiles")
        if isinstance(raw_changes, list):
            rows.extend(raw_changes)
        if isinstance(raw_output_files, list):
            rows.extend(raw_output_files)
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if ExecutionAuditWorkflowService._is_planningtree_path(path):
                return True
        return False

    @staticmethod
    def _output_text_from_changes(changes: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            str(change.get("diff") or "").strip()
            for change in changes
            if str(change.get("diff") or "").strip()
        )

    @staticmethod
    def _should_trigger_live_file_change_hydrate(raw_event: dict[str, Any]) -> bool:
        method = str(raw_event.get("method") or "").strip()
        if method not in {"item/completed", "turn/completed"}:
            return False
        if method == "turn/completed":
            return True
        params = raw_event.get("params", {})
        item = params.get("item", {}) if isinstance(params, dict) else {}
        if not isinstance(item, dict):
            return False
        return str(item.get("kind") or "") == "tool"

    def _hydrate_execution_file_change_diff_from_worktree(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        workspace_root: str | None,
        start_sha: str | None,
        hydrated_by: str = "execution_audit_worktree_diff",
        refresh_synthetic_from_full_diff: bool = False,
    ) -> None:
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return
        if not isinstance(start_sha, str) or not start_sha.strip():
            return
        query_service = self._resolve_thread_query_service()
        if query_service is None:
            return

        class _WorktreeRangeDiffSource(ExecutionFileChangeDiffSource):
            mode = "worktree_range"

            def __init__(
                self,
                *,
                artifact_service: GitArtifactService,
                workspace_root: str,
                start_sha: str,
            ) -> None:
                self._artifact_service = artifact_service
                self._workspace_root = workspace_root
                self._start_sha = start_sha

            def get_diff_for_paths(self, paths: list[str]) -> str:
                return str(
                    self._artifact_service.get_worktree_diff(
                        workspace_root=self._workspace_root,
                        start_sha=self._start_sha,
                        paths=paths,
                    )
                    or ""
                )

            def get_full_diff(self) -> str:
                return str(
                    self._artifact_service.get_worktree_diff(
                        workspace_root=self._workspace_root,
                        start_sha=self._start_sha,
                        paths=None,
                    )
                    or ""
                )

        diff_source = _WorktreeRangeDiffSource(
            artifact_service=self._artifact_service,
            workspace_root=workspace_root,
            start_sha=start_sha,
        )
        hydrator = ExecutionFileChangeHydrator(logger=logger)

        snapshot = self._get_thread_snapshot(
            project_id,
            node_id,
            "execution",
            publish_repairs=False,
            ensure_binding=False,
            allow_thread_read_hydration=False,
        )
        updated_snapshot, pending_events, _counters = hydrator.hydrate_turn_snapshot(
            snapshot=snapshot,
            turn_id=turn_id,
            diff_source=diff_source,
            hydrated_by=hydrated_by,
            project_id=project_id,
            node_id=node_id,
            refresh_synthetic_from_full_diff=refresh_synthetic_from_full_diff,
        )

        if pending_events:
            self._persist_thread_mutation(project_id, node_id, "execution", updated_snapshot, pending_events)

    def review_in_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        response = orchestrator.start_audit(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_workspace_hash=expected_workspace_hash,
        )
        state = orchestrator.get_legacy_workflow_state(project_id, node_id)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="review_in_audit_started")
        return {
            "accepted": True,
            "reviewCycleId": response.get("auditRunId") or response.get("reviewCycleId"),
            "reviewThreadId": response.get("reviewThreadId") or response.get("threadId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def mark_done_from_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        orchestrator = self._require_workflow_orchestrator_v2()
        orchestrator.accept_audit(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_review_commit_sha=expected_review_commit_sha,
        )
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="mark_done_from_audit")
        return orchestrator.get_legacy_workflow_state(project_id, node_id)

    def _run_review_cycle_background(
        self,
        *,
        project_id: str,
        node_id: str,
        cycle_id: str,
        local_turn_id: str,
        thread_id: str,
        prompt: str,
        review_commit_sha: str,
        workspace_root: str | None,
    ) -> None:
        turn_finalized = False
        discovered_review_thread_id: str | None = thread_id
        discovered_review_turn_id: str | None = None
        final_review_text: str | None = None
        review_disposition: str | None = None

        try:
            stream_result = self._resolve_thread_runtime_service().stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="audit",
                thread_id=thread_id,
                turn_id=local_turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only",
                timeout_sec=self._finish_task_service._chat_timeout,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._resolve_thread_runtime_service().outcome_from_turn_status(turn_status)
            if outcome != "completed":
                raise ReviewNotAllowed(
                    f"Audit review run returned unsupported terminal status {turn_status or 'unknown'}."
                )

            discovered_review_thread_id = str(result.get("thread_id") or "").strip() or discovered_review_thread_id
            discovered_review_turn_id = str(result.get("turn_id") or "").strip() or discovered_review_turn_id
            normalized_review_text, normalized_from_json = self._normalize_review_response_text(
                str(result.get("stdout") or "")
            )
            final_review_text = normalized_review_text or final_review_text
            if discovered_review_thread_id:
                self._adopt_review_thread(project_id, node_id, cycle_id, discovered_review_thread_id)
            if not final_review_text:
                final_review_text = "Local review completed without a textual review payload."
            if normalized_from_json and final_review_text:
                self._rewrite_review_turn_assistant_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=local_turn_id,
                    review_text=final_review_text,
                )
            self._ensure_review_summary_item(
                project_id=project_id,
                node_id=node_id,
                thread_id=discovered_review_thread_id or thread_id,
                turn_id=discovered_review_turn_id or local_turn_id,
                review_text=final_review_text,
            )
            self._resolve_thread_runtime_service().complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="audit",
                turn_id=local_turn_id,
                outcome="completed",
            )
            turn_finalized = True
            with self._storage.project_lock(project_id):
                cycles = self._storage.review_cycle_store.read_cycles(project_id, node_id)
                for cycle in cycles:
                    if str(cycle.get("cycleId") or "") != cycle_id:
                        continue
                    cycle["reviewThreadId"] = discovered_review_thread_id
                    cycle["reviewTurnId"] = discovered_review_turn_id
                    cycle["lifecycleStatus"] = "completed"
                    cycle["reviewDisposition"] = review_disposition
                    cycle["finalReviewText"] = final_review_text
                    cycle["completedAt"] = iso_now()
                    break
                self._storage.review_cycle_store.write_cycles(project_id, node_id, cycles)
                state = self._ensure_workflow_state_locked(project_id, node_id)
                if discovered_review_thread_id:
                    state["reviewThreadId"] = discovered_review_thread_id
                state["workflowPhase"] = "audit_decision_pending"
                state["activeReviewCycleId"] = None
                state["latestReviewCycleId"] = cycle_id
                state["currentAuditDecision"] = self._materialize_audit_decision(
                    cycle_id=cycle_id,
                    review_commit_sha=review_commit_sha,
                    final_review_text=final_review_text,
                    review_disposition=review_disposition,
                )
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
        except Exception as exc:
            logger.exception("Audit review cycle failed for %s/%s", project_id, node_id, exc_info=exc)
            if not turn_finalized:
                try:
                    error_item = self._resolve_thread_runtime_service().build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="audit",
                        turn_id=local_turn_id,
                        thread_id=discovered_review_thread_id or thread_id,
                        message=str(exc),
                    )
                    self._resolve_thread_runtime_service().complete_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="audit",
                        turn_id=local_turn_id,
                        outcome="failed",
                        error_item=error_item,
                    )
                except Exception:
                    logger.debug("Failed to finalize review turn %s/%s", project_id, node_id, exc_info=True)
            with self._storage.project_lock(project_id):
                cycles = self._storage.review_cycle_store.read_cycles(project_id, node_id)
                for cycle in cycles:
                    if str(cycle.get("cycleId") or "") != cycle_id:
                        continue
                    cycle["reviewThreadId"] = discovered_review_thread_id
                    cycle["reviewTurnId"] = discovered_review_turn_id
                    cycle["lifecycleStatus"] = "failed"
                    cycle["errorMessage"] = str(exc)
                    cycle["completedAt"] = iso_now()
                    break
                self._storage.review_cycle_store.write_cycles(project_id, node_id, cycles)
                state = self._ensure_workflow_state_locked(project_id, node_id)
                state["workflowPhase"] = "failed"
                state["activeReviewCycleId"] = None
                state["runtimeBlock"] = {"kind": "review_failed", "message": str(exc)}
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
        finally:
            self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="review_cycle_settled")

    def _adopt_review_thread(self, project_id: str, node_id: str, cycle_id: str, review_thread_id: str) -> None:
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("reviewThreadId") or "") != review_thread_id:
                state["reviewThreadId"] = review_thread_id
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
            cycles = self._storage.review_cycle_store.read_cycles(project_id, node_id)
            for cycle in cycles:
                if str(cycle.get("cycleId") or "") != cycle_id:
                    continue
                cycle["reviewThreadId"] = review_thread_id
                break
            self._storage.review_cycle_store.write_cycles(project_id, node_id, cycles)
            self._bind_audit_thread_to_review_thread(project_id, node_id, review_thread_id)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="review_thread_adopted")

    def _ensure_review_summary_item(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        turn_id: str,
        review_text: str,
    ) -> None:
        snapshot = self._get_thread_snapshot(
            project_id,
            node_id,
            "audit",
            publish_repairs=False,
            ensure_binding=False,
            allow_thread_read_hydration=False,
        )
        has_assistant_message = any(
            str(item.get("kind") or "") == "message"
            and str(item.get("role") or "") == "assistant"
            and str(item.get("turnId") or "") == turn_id
            and str(item.get("text") or "").strip()
            for item in snapshot.get("items", [])
        )
        if has_assistant_message:
            return
        item = {
            "id": f"review:{turn_id}:summary",
            "kind": "message",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": max((int(current.get("sequence") or 0) for current in snapshot.get("items", [])), default=0) + 1,
            "createdAt": iso_now(),
            "updatedAt": iso_now(),
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {"workflowReviewSummary": True},
            "role": "assistant",
            "text": review_text,
            "format": "markdown",
        }
        updated, events = self._upsert_item(snapshot, item)
        self._persist_thread_mutation(project_id, node_id, "audit", updated, events)

    @staticmethod
    def _extract_json_object_from_text(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        candidates: list[str] = []
        if raw.startswith("{") and raw.endswith("}"):
            candidates.append(raw)

        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
        if fenced_match:
            candidates.append(fenced_match.group(1).strip())

        if not candidates and raw.startswith("{"):
            candidates.append(raw)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @classmethod
    def _normalize_review_response_text(cls, raw_text: str) -> tuple[str | None, bool]:
        normalized = str(raw_text or "").strip()
        if not normalized:
            return None, False

        payload = cls._extract_json_object_from_text(normalized)
        if payload is None:
            return normalized, False

        for key in ("summary", "review", "final_review_text", "checkpoint_summary"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), True
        return normalized, False

    def _rewrite_review_turn_assistant_message(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        review_text: str,
    ) -> None:
        text = str(review_text or "").strip()
        if not text:
            return

        snapshot = self._get_thread_snapshot(
            project_id,
            node_id,
            "audit",
            publish_repairs=False,
            ensure_binding=False,
            allow_thread_read_hydration=False,
        )
        assistant_messages = [
            item
            for item in snapshot.get("items", [])
            if isinstance(item, dict)
            and str(item.get("kind") or "") == "message"
            and str(item.get("role") or "") == "assistant"
            and str(item.get("turnId") or "") == turn_id
        ]
        if not assistant_messages:
            return

        updated = snapshot
        events: list[dict[str, Any]] = []
        for item in assistant_messages:
            current_text = str(item.get("text") or "").strip()
            if current_text == text:
                continue
            if self._extract_json_object_from_text(current_text) is None:
                continue

            rewritten = copy.deepcopy(item)
            rewritten["text"] = text
            rewritten["updatedAt"] = iso_now()
            if str(rewritten.get("status") or "") != "failed":
                rewritten["status"] = "completed"
            updated, upsert_events = self._upsert_item(updated, rewritten)
            events.extend(upsert_events)

        if events:
            self._persist_thread_mutation(project_id, node_id, "audit", updated, events)

    def _materialize_execution_decision(
        self,
        *,
        run_id: str,
        turn_id: str,
        candidate_workspace_hash: str,
        summary_text: str | None,
    ) -> dict[str, Any]:
        return {
            "status": "current",
            "sourceExecutionRunId": run_id,
            "executionTurnId": turn_id,
            "candidateWorkspaceHash": candidate_workspace_hash,
            "summaryText": summary_text,
            "createdAt": iso_now(),
        }

    def _materialize_audit_decision(
        self,
        *,
        cycle_id: str,
        review_commit_sha: str,
        final_review_text: str | None,
        review_disposition: str | None,
    ) -> dict[str, Any]:
        return {
            "status": "current",
            "sourceReviewCycleId": cycle_id,
            "reviewCommitSha": review_commit_sha,
            "finalReviewText": final_review_text,
            "reviewDisposition": review_disposition,
            "createdAt": iso_now(),
        }

    def _materialize_latest_commit(
        self,
        *,
        source_action: str,
        commit_result: WorkspaceCommitResult,
    ) -> dict[str, Any]:
        return {
            "sourceAction": source_action,
            "initialSha": commit_result["initialSha"],
            "headSha": commit_result["headSha"],
            "commitMessage": commit_result["commitMessage"],
            "committed": commit_result["committed"],
            "recordedAt": iso_now(),
        }

    def _ensure_workflow_state_locked(self, project_id: str, node_id: str) -> dict[str, Any]:
        state = self._storage.workflow_state_store.read_state(project_id, node_id)
        if state is None:
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            workspace_root = self._finish_task_service._workspace_root_from_snapshot(snapshot)
            audit_lineage_thread_id = self._ensure_audit_lineage_thread_id(project_id, node_id, workspace_root)
            state = self._storage.workflow_state_store.default_state(node_id)
            state["workflowPhase"] = "done" if str(node.get("status") or "") == "done" else "idle"
            state["auditLineageThreadId"] = audit_lineage_thread_id
        execution_entry = self._storage.thread_registry_store.read_entry(project_id, node_id, "execution")
        # Keep workflow-state askThreadId aligned with the ask registry entry so
        # /v3 by-id asks loaded from workflow state do not drift to stale ids.
        ask_thread_id = self._resolve_ask_thread_id(project_id, node_id)
        current_ask_thread_id = str(state.get("askThreadId") or "").strip() or None
        if current_ask_thread_id != ask_thread_id:
            state["askThreadId"] = ask_thread_id
        if not state.get("executionThreadId"):
            execution_thread_id = str(execution_entry.get("threadId") or "").strip()
            if execution_thread_id:
                state["executionThreadId"] = execution_thread_id
        audit_entry = self._storage.thread_registry_store.read_entry(project_id, node_id, "audit")
        if not state.get("auditLineageThreadId"):
            audit_thread_id = str(audit_entry.get("threadId") or "").strip()
            if audit_thread_id:
                state["auditLineageThreadId"] = audit_thread_id
        return state

    def _resolve_ask_thread_id(self, project_id: str, node_id: str) -> str | None:
        ask_entry = self._storage.thread_registry_store.read_entry(
            project_id,
            node_id,
            "ask_planning",
        )
        ask_thread_id = str(ask_entry.get("threadId") or "").strip()
        if ask_thread_id:
            return ask_thread_id
        legacy_session = self._storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role="ask_planning",
        )
        legacy_thread_id = str(legacy_session.get("thread_id") or "").strip()
        if not legacy_thread_id:
            return None
        seeded_entry = dict(ask_entry)
        seeded_entry["threadId"] = legacy_thread_id
        seeded_entry["forkedFromThreadId"] = (
            str(legacy_session.get("forked_from_thread_id") or "").strip() or None
        )
        seeded_entry["forkedFromNodeId"] = (
            str(legacy_session.get("forked_from_node_id") or "").strip() or None
        )
        seeded_entry["forkedFromRole"] = (
            str(legacy_session.get("forked_from_role") or "").strip() or None
        )
        seeded_entry["forkReason"] = (
            str(legacy_session.get("fork_reason") or "").strip() or None
        )
        seeded_entry["lineageRootThreadId"] = (
            str(legacy_session.get("lineage_root_thread_id") or "").strip() or None
        )
        self._storage.thread_registry_store.write_entry(
            project_id,
            node_id,
            "ask_planning",
            seeded_entry,
        )
        return legacy_thread_id

    def _ensure_audit_lineage_thread_id(self, project_id: str, node_id: str, workspace_root: str | None) -> str:
        try:
            entry = self._finish_task_service._thread_lineage_service.ensure_thread_binding_v2(
                project_id,
                node_id,
                "audit",
                workspace_root,
                writable_roots=None,
            )
        except CodexTransportError as exc:
            raise AuditLineageUnavailable(str(exc)) from exc
        except ValueError as exc:
            raise AuditLineageUnavailable(str(exc)) from exc
        thread_id = str(entry.get("threadId") or "").strip()
        if not thread_id:
            raise AuditLineageUnavailable("Audit lineage bootstrap did not return a thread id.")
        return thread_id

    def _bind_audit_thread_to_review_thread(self, project_id: str, node_id: str, review_thread_id: str) -> None:
        entry = self._storage.thread_registry_store.read_entry(project_id, node_id, "audit")
        entry["threadId"] = review_thread_id
        entry["forkReason"] = "local_review_thread"
        self._storage.thread_registry_store.write_entry(project_id, node_id, "audit", entry)

    def _build_local_user_item(
        self,
        *,
        snapshot: dict[str, Any],
        thread_id: str,
        turn_id: str,
        text: str,
    ) -> dict[str, Any]:
        now = iso_now()
        return {
            "id": f"turn:{turn_id}:user",
            "kind": "message",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1,
            "createdAt": now,
            "updatedAt": now,
            "status": "completed",
            "source": "local",
            "tone": "neutral",
            "metadata": {},
            "role": "user",
            "text": text,
            "format": "markdown",
        }

    def _resolve_execution_summary_text_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        run_id: str | None,
    ) -> str:
        target_run_id = str(run_id or "").strip()
        if not target_run_id:
            return _HANDOFF_SUMMARY_PLACEHOLDER
        runs = self._storage.execution_run_store.read_runs(project_id, node_id)
        for run in runs:
            if str(run.get("runId") or "").strip() != target_run_id:
                continue
            summary_text = str(run.get("summaryText") or "").strip()
            return summary_text or _HANDOFF_SUMMARY_PLACEHOLDER
        return _HANDOFF_SUMMARY_PLACEHOLDER

    def _resolve_execution_run_id_for_audit_mark_done_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        state: dict[str, Any],
        current_audit_decision: dict[str, Any],
    ) -> str | None:
        cycle_id = str(current_audit_decision.get("sourceReviewCycleId") or "").strip()
        if cycle_id:
            review_cycles = self._storage.review_cycle_store.read_cycles(project_id, node_id)
            for cycle in review_cycles:
                if str(cycle.get("cycleId") or "").strip() != cycle_id:
                    continue
                run_id = str(cycle.get("sourceExecutionRunId") or "").strip()
                if run_id:
                    return run_id
                break
        latest_run_id = str(state.get("latestExecutionRunId") or "").strip()
        return latest_run_id or None

    def _upsert_handoff_summary_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
        snapshot: Any,
        node: Any,
        summary_text: str,
    ) -> None:
        root = str(workspace_root or "").strip()
        if not root:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        target = Path(root).expanduser().resolve() / _HANDOFF_DOCS_DIR / _HANDOFF_FILE_NAME
        if target.exists():
            content = load_text(target)
            if not content.strip():
                content = _HANDOFF_FILE_HEADER
        else:
            content = _HANDOFF_FILE_HEADER

        node_payload = node if isinstance(node, dict) else {}
        block = self._render_handoff_block(
            node_id=node_id,
            node_label=self._node_label_for_handoff(node_payload),
            summary_text=str(summary_text or "").strip() or _HANDOFF_SUMMARY_PLACEHOLDER,
        )
        ordered_node_ids = self._handoff_task_node_order(snapshot) if isinstance(snapshot, dict) else []
        updated = self._upsert_handoff_block_content(
            content=content,
            node_id=node_id,
            block=block,
            ordered_node_ids=ordered_node_ids,
        )
        if updated == content:
            return
        atomic_write_text(target, updated)

    @staticmethod
    def _node_label_for_handoff(node: dict[str, Any]) -> str:
        hierarchical_number = str(node.get("hierarchical_number") or "").strip()
        title = str(node.get("title") or "").strip() or "Task"
        return f"{hierarchical_number} {title}".strip()

    @staticmethod
    def _render_handoff_block(*, node_id: str, node_label: str, summary_text: str) -> str:
        normalized_summary = summary_text.rstrip()
        return (
            f"<!-- PT_HANDOFF_NODE:{node_id} -->\n"
            f"## {node_label}\n\n"
            f"{normalized_summary}\n"
            f"<!-- /PT_HANDOFF_NODE:{node_id} -->\n"
        )

    def _upsert_handoff_block_content(
        self,
        *,
        content: str,
        node_id: str,
        block: str,
        ordered_node_ids: list[str],
    ) -> str:
        matches = list(_HANDOFF_NODE_BLOCK_RE.finditer(content))
        ranges_by_node_id: dict[str, tuple[int, int]] = {}
        for match in matches:
            match_node_id = str(match.group("node_id") or "").strip()
            if not match_node_id or match_node_id in ranges_by_node_id:
                continue
            ranges_by_node_id[match_node_id] = (match.start(), match.end())

        existing = ranges_by_node_id.get(node_id)
        if existing is not None:
            start, end = existing
            return f"{content[:start]}{block}{content[end:]}"

        insert_at = self._choose_handoff_insert_offset(
            content=content,
            ranges_by_node_id=ranges_by_node_id,
            ordered_node_ids=ordered_node_ids,
            target_node_id=node_id,
        )
        prefix = content[:insert_at]
        suffix = content[insert_at:]
        before = "" if not prefix or prefix.endswith("\n") else "\n"
        after = "" if not suffix or suffix.startswith("\n") else "\n"
        return f"{prefix}{before}{block}{after}{suffix}"

    @staticmethod
    def _choose_handoff_insert_offset(
        *,
        content: str,
        ranges_by_node_id: dict[str, tuple[int, int]],
        ordered_node_ids: list[str],
        target_node_id: str,
    ) -> int:
        if ranges_by_node_id and ordered_node_ids:
            try:
                target_index = ordered_node_ids.index(target_node_id)
            except ValueError:
                target_index = -1
            if target_index >= 0:
                for previous_id in reversed(ordered_node_ids[:target_index]):
                    previous_range = ranges_by_node_id.get(previous_id)
                    if previous_range is not None:
                        return previous_range[1]
                for next_id in ordered_node_ids[target_index + 1 :]:
                    next_range = ranges_by_node_id.get(next_id)
                    if next_range is not None:
                        return next_range[0]
        return len(content)

    @staticmethod
    def _handoff_task_node_order(snapshot: dict[str, Any]) -> list[str]:
        tree_state = snapshot.get("tree_state")
        if not isinstance(tree_state, dict):
            return []
        node_index = tree_state.get("node_index")
        if not isinstance(node_index, dict):
            return []
        root_node_id = str(tree_state.get("root_node_id") or "").strip()
        if not root_node_id:
            return []

        ordered_ids: list[str] = []
        visited: set[str] = set()

        def walk(node_id: str) -> None:
            if not node_id or node_id in visited:
                return
            visited.add(node_id)
            node = node_index.get(node_id)
            if not isinstance(node, dict):
                return
            node_kind = str(node.get("node_kind") or "").strip()
            if node_id == root_node_id:
                node_kind = "root"
            elif not node_kind:
                node_kind = "original"
            if node_kind in {"root", "original"}:
                ordered_ids.append(node_id)
            child_ids = node.get("child_ids")
            if not isinstance(child_ids, list):
                return
            for raw_child_id in child_ids:
                child_id = str(raw_child_id or "").strip()
                if child_id:
                    walk(child_id)

        walk(root_node_id)
        return ordered_ids

    def _update_execution_run_decision(
        self,
        *,
        project_id: str,
        node_id: str,
        run_id: str,
        committed_head_sha: str,
        decision: str,
    ) -> None:
        runs = self._storage.execution_run_store.read_runs(project_id, node_id)
        for run in runs:
            if str(run.get("runId") or "") != run_id:
                continue
            run["committedHeadSha"] = committed_head_sha
            run["decision"] = decision
            run["decidedAt"] = iso_now()
            break
        self._storage.execution_run_store.write_runs(project_id, node_id, runs)

    def _complete_node_progression(
        self,
        project_id: str,
        node_id: str,
        *,
        accepted_sha: str,
        summary_text: str | None,
    ) -> None:
        activated_sibling_id: str | None = None
        activated_review_node_id: str | None = None
        activated_workspace_root: str | None = None
        rollup_ready_review_node_id: str | None = None

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node["status"] = "done"
            parent_id = str(node.get("parent_id") or "").strip()
            parent = node_by_id.get(parent_id) if parent_id else None
            review_node_id = str(parent.get("review_node_id") or "").strip() if isinstance(parent, dict) else ""
            if review_node_id:
                self._storage.review_state_store.add_checkpoint(
                    project_id,
                    review_node_id,
                    sha=accepted_sha,
                    summary=summary_text,
                    source_node_id=node_id,
                )
                activated_review_node_id = review_node_id
                if self._review_service is not None:
                    (
                        activated_sibling_id,
                        rollup_ready_review_node_id,
                    ) = self._review_service._try_activate_next_sibling(
                        project_id,
                        parent,
                        review_node_id,
                        snapshot,
                        node_by_id,
                    )
                    if activated_sibling_id:
                        activated_workspace_root = self._finish_task_service._workspace_root_from_snapshot(snapshot)
            elif isinstance(parent, dict):
                unlocked_id = self._tree_service.unlock_next_sibling(node, node_by_id)
                if unlocked_id:
                    snapshot["tree_state"]["active_node_id"] = unlocked_id
                    activated_sibling_id = unlocked_id

            now = iso_now()
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            self._storage.project_store.touch_meta(project_id, now)

        if rollup_ready_review_node_id and self._review_service is not None:
            try:
                self._review_service.start_review_rollup(project_id, rollup_ready_review_node_id)
            except Exception:
                logger.debug(
                    "Failed to auto-start review rollup for %s/%s",
                    project_id,
                    rollup_ready_review_node_id,
                    exc_info=True,
                )

        if activated_sibling_id and activated_review_node_id and activated_workspace_root and self._review_service is not None:
            self._review_service._bootstrap_child_audit_best_effort(
                project_id,
                activated_review_node_id,
                activated_sibling_id,
                activated_workspace_root,
            )

    def _publish_workflow_refresh(self, *, project_id: str, node_id: str, reason: str) -> None:
        if self._workflow_event_publisher is None:
            return
        view = self.get_workflow_state(project_id, node_id)
        self._workflow_event_publisher.publish_workflow_updated(
            project_id=project_id,
            node_id=node_id,
            workflow_phase=str(view.get("workflowPhase") or ""),
            active_execution_run_id=str(view.get("activeExecutionRunId") or "") or None,
            active_review_cycle_id=str(view.get("activeReviewCycleId") or "") or None,
        )
        self._workflow_event_publisher.publish_detail_invalidate(
            project_id=project_id,
            node_id=node_id,
            reason=reason,
        )

    def _get_cached_mutation(
        self,
        project_id: str,
        node_id: str,
        action: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not idempotency_key.strip():
            raise FinishTaskNotAllowed("idempotencyKey is required.")
        with self._storage.project_lock(project_id):
            state = self._storage.workflow_state_store.read_state(project_id, node_id)
            if not isinstance(state, dict):
                return None
            cache_key = f"{action}:{idempotency_key}"
            cached = state.get("mutationCache", {}).get(cache_key)
            return copy.deepcopy(cached) if isinstance(cached, dict) else None

    def _store_cached_mutation(
        self,
        project_id: str,
        node_id: str,
        action: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> None:
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            cache_key = f"{action}:{idempotency_key}"
            mutation_cache = state.get("mutationCache")
            if not isinstance(mutation_cache, dict):
                mutation_cache = {}
            mutation_cache[cache_key] = copy.deepcopy(payload)
            state["mutationCache"] = mutation_cache
            self._storage.workflow_state_store.write_state(project_id, node_id, state)


