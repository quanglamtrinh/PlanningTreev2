from __future__ import annotations

import copy
import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai.execution_prompt_builder import build_execution_prompt
from backend.ai.split_context_builder import build_split_context
from backend.conversation.projector.thread_event_projector import apply_raw_event, upsert_item
from backend.conversation.services.thread_runtime_service import ThreadRuntimeService
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.errors.app_errors import FinishTaskNotAllowed, NodeNotFound, ReviewNotAllowed
from backend.services.finish_task_service import FinishTaskService
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.review_service import ReviewService
from backend.services.tree_service import TreeService
from backend.services.workspace_sha import compute_workspace_sha
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)


class WorkflowDecisionService:
    def build_view(self, state: dict[str, Any]) -> dict[str, Any]:
        phase = str(state.get("workflowPhase") or "idle")
        current_execution_decision = copy.deepcopy(state.get("currentExecutionDecision"))
        current_audit_decision = copy.deepcopy(state.get("currentAuditDecision"))
        return {
            "nodeId": state.get("nodeId"),
            "workflowPhase": phase,
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
    def build_execution_followup_prompt(
        *,
        spec_content: str,
        frame_content: str,
        task_context: dict[str, Any],
        instruction_text: str,
    ) -> str:
        base = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
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
        base = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
        improve = (
            "Latest local review feedback:\n"
            "```markdown\n"
            f"{review_text.strip()}\n"
            "```\n\n"
            "Improve the implementation to address this review feedback now. "
            "Keep the solution aligned with the confirmed task and existing codebase."
        )
        return f"{base}\n\n{improve}"


class GitArtifactService:
    def __init__(self, git_checkpoint_service: GitCheckpointService | None) -> None:
        self._git_checkpoint_service = git_checkpoint_service

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
    ) -> str:
        if self._git_checkpoint_service is None:
            raise FinishTaskNotAllowed("Git checkpoint service is unavailable.")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(workspace_root).expanduser().resolve()
        commit_message = self._git_checkpoint_service.build_commit_message(
            hierarchical_number,
            f"{verb} {title}".strip(),
        )
        committed_sha = self._git_checkpoint_service.commit_if_changed(project_path, commit_message)
        if committed_sha:
            return committed_sha
        return self._git_checkpoint_service.capture_head_sha(project_path)


class ExecutionAuditWorkflowService:
    def __init__(
        self,
        *,
        storage: Storage,
        tree_service: TreeService,
        finish_task_service: FinishTaskService,
        review_service: ReviewService,
        thread_runtime_service_v2: ThreadRuntimeService,
        workflow_event_publisher_v2: WorkflowEventPublisher,
        git_checkpoint_service: GitCheckpointService | None,
        codex_client: Any,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._finish_task_service = finish_task_service
        self._review_service = review_service
        self._thread_runtime_service_v2 = thread_runtime_service_v2
        self._workflow_event_publisher_v2 = workflow_event_publisher_v2
        self._codex_client = codex_client
        self._decision_service = WorkflowDecisionService()
        self._metadata_service = WorkflowMetadataService(tree_service, finish_task_service)
        self._artifact_service = GitArtifactService(git_checkpoint_service)

    def get_workflow_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            self._storage.workflow_state_store.write_state(project_id, node_id, state)
            return self._decision_service.build_view(state)

    def finish_task(self, project_id: str, node_id: str, *, idempotency_key: str) -> dict[str, Any]:
        cached = self._get_cached_mutation(project_id, node_id, "finish_task", idempotency_key)
        if cached is not None:
            return cached
        metadata = self._metadata_service.load_execution_metadata(project_id, node_id, validate_finish_task=True)
        prompt = build_execution_prompt(
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            task_context=metadata["taskContext"],
        )
        response = self._start_execution_run(
            project_id=project_id,
            node_id=node_id,
            idempotency_key=idempotency_key,
            prompt=prompt,
            start_sha=str(metadata["initialSha"]),
            trigger_kind="finish_task",
            source_review_cycle_id=None,
            workspace_root=metadata["workspaceRoot"],
            summary_seed=None,
            local_user_text=None,
        )
        self._store_cached_mutation(project_id, node_id, "finish_task", idempotency_key, response)
        return response

    def start_execution_followup(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        text: str,
    ) -> dict[str, Any]:
        cached = self._get_cached_mutation(project_id, node_id, "execution_follow_up", idempotency_key)
        if cached is not None:
            return cached
        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        prompt = self._metadata_service.build_execution_followup_prompt(
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            task_context=metadata["taskContext"],
            instruction_text=text,
        )
        response = self._start_execution_run(
            project_id=project_id,
            node_id=node_id,
            idempotency_key=idempotency_key,
            prompt=prompt,
            start_sha=str(metadata["initialSha"]),
            trigger_kind="follow_up_message",
            source_review_cycle_id=None,
            workspace_root=metadata["workspaceRoot"],
            summary_seed=text.strip() or None,
            local_user_text=text,
        )
        self._store_cached_mutation(project_id, node_id, "execution_follow_up", idempotency_key, response)
        return response

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
        return self._thread_runtime_service_v2._query_service.get_thread_snapshot(
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
        snapshot = self._thread_runtime_service_v2._query_service.build_stream_snapshot(
            project_id,
            node_id,
            thread_role,
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
        cached = self._get_cached_mutation(project_id, node_id, "mark_done_from_execution", idempotency_key)
        if cached is not None:
            return cached

        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("workflowPhase") or "") != "execution_decision_pending":
                raise FinishTaskNotAllowed("Mark Done from Execution is only available in execution_decision_pending.")
            current_execution_decision = state.get("currentExecutionDecision")
            if not isinstance(current_execution_decision, dict):
                raise FinishTaskNotAllowed("No current execution decision is available.")
            metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
            self._artifact_service.require_workspace_hash(metadata["workspaceRoot"], expected_workspace_hash)
            accepted_sha = self._artifact_service.commit_workspace(
                workspace_root=metadata["workspaceRoot"],
                hierarchical_number=str(metadata["node"].get("hierarchical_number") or "1"),
                title=str(metadata["node"].get("title") or "task").strip() or "task",
                verb="done",
            )
            run_id = str(current_execution_decision.get("sourceExecutionRunId") or "")
            runs = self._storage.execution_run_store.read_runs(project_id, node_id)
            summary_text: str | None = None
            for run in runs:
                if str(run.get("runId") or "") != run_id:
                    continue
                run["committedHeadSha"] = accepted_sha
                run["decision"] = "marked_done"
                run["decidedAt"] = iso_now()
                summary_text = str(run.get("summaryText") or "").strip() or None
                break
            self._storage.execution_run_store.write_runs(project_id, node_id, runs)
            state["acceptedSha"] = accepted_sha
            state["workflowPhase"] = "done"
            state["activeExecutionRunId"] = None
            self._storage.workflow_state_store.write_state(project_id, node_id, state)

        self._complete_node_progression(project_id, node_id, accepted_sha=accepted_sha, summary_text=summary_text)
        response = self.get_workflow_state(project_id, node_id)
        self._store_cached_mutation(project_id, node_id, "mark_done_from_execution", idempotency_key, response)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="mark_done_from_execution")
        return response

    def improve_in_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        cached = self._get_cached_mutation(project_id, node_id, "improve_in_execution", idempotency_key)
        if cached is not None:
            return cached

        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("workflowPhase") or "") != "audit_decision_pending":
                raise ReviewNotAllowed("Improve in Execution is only available in audit_decision_pending.")
            current_audit_decision = state.get("currentAuditDecision")
            if not isinstance(current_audit_decision, dict):
                raise ReviewNotAllowed("No current audit decision is available.")
            metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
            self._artifact_service.require_head_sha(metadata["workspaceRoot"], expected_review_commit_sha)
            review_text = str(current_audit_decision.get("finalReviewText") or "").strip()
            if not review_text:
                raise ReviewNotAllowed("No completed local review text is available for improvement.")

        prompt = self._metadata_service.build_improve_prompt(
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            task_context=metadata["taskContext"],
            review_text=review_text,
        )
        response = self._start_execution_run(
            project_id=project_id,
            node_id=node_id,
            idempotency_key=idempotency_key,
            prompt=prompt,
            start_sha=expected_review_commit_sha,
            trigger_kind="improve_from_review",
            source_review_cycle_id=str(state.get("latestReviewCycleId") or "") or None,
            workspace_root=metadata["workspaceRoot"],
            summary_seed=review_text,
            local_user_text=None,
        )
        self._store_cached_mutation(project_id, node_id, "improve_in_execution", idempotency_key, response)
        return response

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
            snapshot = self._thread_runtime_service_v2._query_service.get_thread_snapshot(
                project_id,
                node_id,
                "execution",
                publish_repairs=False,
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
            self._thread_runtime_service_v2.begin_turn(
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
    ) -> None:
        turn_finalized = False
        try:
            stream_result = self._thread_runtime_service_v2.stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                thread_id=thread_id,
                turn_id=turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                timeout_sec=self._finish_task_service._chat_timeout,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._thread_runtime_service_v2.outcome_from_turn_status(turn_status)
            if outcome != "completed":
                raise FinishTaskNotAllowed(
                    f"Execution run returned unsupported terminal status {turn_status or 'unknown'}."
                )
            self._thread_runtime_service_v2.complete_turn(
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
                    error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        thread_id=thread_id,
                        message=str(exc),
                    )
                    self._thread_runtime_service_v2.complete_turn(
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

    def review_in_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        cached = self._get_cached_mutation(project_id, node_id, "review_in_audit", idempotency_key)
        if cached is not None:
            return cached

        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("workflowPhase") or "") != "execution_decision_pending":
                raise ReviewNotAllowed("Review in Audit is only available in execution_decision_pending.")
            current_execution_decision = state.get("currentExecutionDecision")
            if not isinstance(current_execution_decision, dict):
                raise ReviewNotAllowed("No current execution decision is available.")
            self._artifact_service.require_workspace_hash(metadata["workspaceRoot"], expected_workspace_hash)
            review_commit_sha = self._artifact_service.commit_workspace(
                workspace_root=metadata["workspaceRoot"],
                hierarchical_number=str(metadata["node"].get("hierarchical_number") or "1"),
                title=str(metadata["node"].get("title") or "task").strip() or "task",
                verb="review",
            )
            audit_lineage_thread_id = str(state.get("auditLineageThreadId") or "").strip()
            if not audit_lineage_thread_id:
                audit_lineage_thread_id = self._ensure_audit_lineage_thread_id(project_id, node_id, metadata["workspaceRoot"])
                state["auditLineageThreadId"] = audit_lineage_thread_id

            review_thread_id = str(state.get("reviewThreadId") or "").strip() or None
            delivery_kind = "inline" if review_thread_id else "detached"
            cycle_id = new_id("review_cycle")
            local_turn_id = new_id("review_turn")
            source_execution_run_id = str(current_execution_decision.get("sourceExecutionRunId") or "")
            cycle = {
                "cycleId": cycle_id,
                "projectId": project_id,
                "nodeId": node_id,
                "sourceExecutionRunId": source_execution_run_id,
                "auditLineageThreadId": audit_lineage_thread_id,
                "reviewThreadId": review_thread_id,
                "reviewTurnId": None,
                "reviewCommitSha": review_commit_sha,
                "deliveryKind": delivery_kind,
                "clientRequestId": idempotency_key,
                "lifecycleStatus": "running",
                "reviewDisposition": None,
                "finalReviewText": None,
                "errorMessage": None,
                "startedAt": iso_now(),
                "completedAt": None,
            }
            self._storage.review_cycle_store.append_cycle(project_id, node_id, cycle)
            self._update_execution_run_decision(
                project_id=project_id,
                node_id=node_id,
                run_id=source_execution_run_id,
                committed_head_sha=review_commit_sha,
                decision="sent_to_review",
            )
            state["workflowPhase"] = "audit_running"
            state["activeReviewCycleId"] = cycle_id
            state["latestReviewCycleId"] = cycle_id
            state["activeExecutionRunId"] = None
            self._storage.workflow_state_store.write_state(project_id, node_id, state)

        if review_thread_id:
            self._bind_audit_thread_to_review_thread(project_id, node_id, review_thread_id)
        self._thread_runtime_service_v2.begin_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role="audit",
            origin="workflow_review",
            created_items=[],
            turn_id=local_turn_id,
        )
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="review_in_audit_started")
        threading.Thread(
            target=self._run_review_cycle_background,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "cycle_id": cycle_id,
                "local_turn_id": local_turn_id,
                "source_thread_id": review_thread_id or audit_lineage_thread_id,
                "delivery_kind": delivery_kind,
                "review_commit_sha": review_commit_sha,
                "client_request_id": idempotency_key,
                "workspace_root": metadata["workspaceRoot"],
            },
            daemon=True,
        ).start()
        response = {
            "accepted": True,
            "reviewCycleId": cycle_id,
            "reviewThreadId": review_thread_id,
            "workflowPhase": "audit_running",
        }
        self._store_cached_mutation(project_id, node_id, "review_in_audit", idempotency_key, response)
        return response

    def mark_done_from_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        cached = self._get_cached_mutation(project_id, node_id, "mark_done_from_audit", idempotency_key)
        if cached is not None:
            return cached

        with self._storage.project_lock(project_id):
            state = self._ensure_workflow_state_locked(project_id, node_id)
            if str(state.get("workflowPhase") or "") != "audit_decision_pending":
                raise ReviewNotAllowed("Mark Done from Audit is only available in audit_decision_pending.")
            current_audit_decision = state.get("currentAuditDecision")
            if not isinstance(current_audit_decision, dict):
                raise ReviewNotAllowed("No current audit decision is available.")
            metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
            self._artifact_service.require_head_sha(metadata["workspaceRoot"], expected_review_commit_sha)
            state["acceptedSha"] = expected_review_commit_sha
            state["workflowPhase"] = "done"
            state["activeReviewCycleId"] = None
            self._storage.workflow_state_store.write_state(project_id, node_id, state)
            review_cycles = self._storage.review_cycle_store.read_cycles(project_id, node_id)
            summary_text: str | None = None
            cycle_id = str(current_audit_decision.get("sourceReviewCycleId") or "")
            for cycle in review_cycles:
                if str(cycle.get("cycleId") or "") != cycle_id:
                    continue
                summary_text = str(cycle.get("finalReviewText") or "").strip() or None
                break

        self._complete_node_progression(project_id, node_id, accepted_sha=expected_review_commit_sha, summary_text=summary_text)
        response = self.get_workflow_state(project_id, node_id)
        self._store_cached_mutation(project_id, node_id, "mark_done_from_audit", idempotency_key, response)
        self._publish_workflow_refresh(project_id=project_id, node_id=node_id, reason="mark_done_from_audit")
        return response

    def _run_review_cycle_background(
        self,
        *,
        project_id: str,
        node_id: str,
        cycle_id: str,
        local_turn_id: str,
        source_thread_id: str,
        delivery_kind: str,
        review_commit_sha: str,
        client_request_id: str,
        workspace_root: str | None,
    ) -> None:
        turn_finalized = False
        discovered_review_thread_id: str | None = None
        discovered_review_turn_id: str | None = None
        final_review_text: str | None = None
        review_disposition: str | None = None

        def handle_raw_event(raw_event: dict[str, Any]) -> None:
            nonlocal discovered_review_thread_id, discovered_review_turn_id, final_review_text, review_disposition
            params = raw_event.get("params", {})
            if not isinstance(params, dict):
                params = {}
            thread_id_candidate = str(
                raw_event.get("review_thread_id")
                or raw_event.get("thread_id")
                or params.get("reviewThreadId")
                or params.get("threadId")
                or ""
            ).strip()
            if thread_id_candidate:
                discovered_review_thread_id = thread_id_candidate
                self._adopt_review_thread(project_id, node_id, cycle_id, thread_id_candidate)

            review_turn_candidate = str(
                raw_event.get("review_turn_id")
                or raw_event.get("turn_id")
                or params.get("reviewTurnId")
                or params.get("turnId")
                or ""
            ).strip()
            if review_turn_candidate:
                discovered_review_turn_id = review_turn_candidate

            if str(raw_event.get("method") or "") == "exitedReviewMode":
                review_payload = params.get("exitedReviewMode")
                if not isinstance(review_payload, dict):
                    review_payload = params
                text = str(review_payload.get("review") or "").strip()
                disposition = str(review_payload.get("disposition") or review_payload.get("result") or "").strip() or None
                if text:
                    final_review_text = text
                if disposition:
                    review_disposition = disposition

            current = self._thread_runtime_service_v2._query_service.get_thread_snapshot(
                project_id,
                node_id,
                "audit",
                publish_repairs=False,
                ensure_binding=False,
                allow_thread_read_hydration=False,
            )
            updated, events = apply_raw_event(current, raw_event)
            if events:
                self._thread_runtime_service_v2._query_service.persist_thread_mutation(
                    project_id,
                    node_id,
                    "audit",
                    updated,
                    events,
                )

        try:
            review_result = self._codex_client.start_review_streaming(
                thread_id=source_thread_id,
                target_sha=review_commit_sha,
                target_title=f"Review commit {review_commit_sha}",
                delivery=delivery_kind if delivery_kind == "detached" else None,
                client_request_id=client_request_id,
                timeout_sec=self._finish_task_service._chat_timeout,
                on_raw_event=handle_raw_event,
            )
            discovered_review_thread_id = str(review_result.get("review_thread_id") or "").strip() or discovered_review_thread_id
            discovered_review_turn_id = str(review_result.get("review_turn_id") or "").strip() or discovered_review_turn_id
            final_review_text = str(review_result.get("review") or "").strip() or final_review_text
            review_disposition = str(review_result.get("review_disposition") or "").strip() or review_disposition
            if discovered_review_thread_id:
                self._adopt_review_thread(project_id, node_id, cycle_id, discovered_review_thread_id)
            if not final_review_text:
                final_review_text = "Local review completed without a textual review payload."
            self._ensure_review_summary_item(
                project_id=project_id,
                node_id=node_id,
                thread_id=discovered_review_thread_id or source_thread_id,
                turn_id=discovered_review_turn_id or local_turn_id,
                review_text=final_review_text,
            )
            self._thread_runtime_service_v2.complete_turn(
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
                    error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="audit",
                        turn_id=local_turn_id,
                        thread_id=discovered_review_thread_id or source_thread_id,
                        message=str(exc),
                    )
                    self._thread_runtime_service_v2.complete_turn(
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
        snapshot = self._thread_runtime_service_v2._query_service.get_thread_snapshot(
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
        updated, events = upsert_item(snapshot, item)
        self._thread_runtime_service_v2._query_service.persist_thread_mutation(
            project_id,
            node_id,
            "audit",
            updated,
            events,
        )

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

    def _ensure_audit_lineage_thread_id(self, project_id: str, node_id: str, workspace_root: str | None) -> str:
        entry = self._finish_task_service._thread_lineage_service.ensure_thread_binding_v2(
            project_id,
            node_id,
            "audit",
            workspace_root,
            writable_roots=None,
        )
        thread_id = str(entry.get("threadId") or "").strip()
        if not thread_id:
            raise ReviewNotAllowed("Audit lineage bootstrap did not return a thread id.")
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
        if self._workflow_event_publisher_v2 is None:
            return
        view = self.get_workflow_state(project_id, node_id)
        self._workflow_event_publisher_v2.publish_workflow_updated(
            project_id=project_id,
            node_id=node_id,
            workflow_phase=str(view.get("workflowPhase") or ""),
            active_execution_run_id=str(view.get("activeExecutionRunId") or "") or None,
            active_review_cycle_id=str(view.get("activeReviewCycleId") or "") or None,
        )
        self._workflow_event_publisher_v2.publish_detail_invalidate(
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
