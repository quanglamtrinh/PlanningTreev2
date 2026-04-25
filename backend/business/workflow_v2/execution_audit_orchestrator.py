from __future__ import annotations

import copy
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable

from backend.ai.execution_prompt_builder import build_execution_prompt
from backend.ai.chat_prompt_builder import build_package_review_prompt
from backend.business.workflow_v2.errors import (
    WorkflowActionNotAllowedError,
    WorkflowArtifactVersionConflictError,
    WorkflowIdempotencyConflictError,
)
from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.models import (
    AuditRunV2,
    ExecutionRunV2,
    NodeWorkflowStateV2,
    WorkflowAction,
    WorkflowPhase,
    utc_now_iso,
    workflow_state_to_response,
)
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import (
    complete_audit as transition_complete_audit,
    complete_execution as transition_complete_execution,
    derive_allowed_actions,
    improve_execution as transition_improve_execution,
    mark_done_from_audit as transition_mark_done_from_audit,
    mark_done_from_execution as transition_mark_done_from_execution,
    start_audit as transition_start_audit,
    start_execution as transition_start_execution,
    start_package_review as transition_start_package_review,
)
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.business.workflow_v2.execution_audit_helpers import GitArtifactService, WorkflowMetadataService
from backend.errors.app_errors import AppError, NodeNotFound
from backend.session_core_v2.errors import SessionCoreError
from backend.storage.file_utils import iso_now, new_id

_HANDOFF_SUMMARY_PLACEHOLDER = "Implementation completed. No execution summary was captured."
logger = logging.getLogger(__name__)


class ExecutionAuditOrchestratorV2:
    def __init__(
        self,
        *,
        repository: WorkflowStateRepositoryV2,
        thread_binding_service: ThreadBindingServiceV2,
        session_manager: Any,
        event_publisher: WorkflowEventPublisherV2 | None,
        storage: Any,
        tree_service: Any,
        finish_task_service: Any,
        review_service: Any | None,
        git_checkpoint_service: Any | None,
    ) -> None:
        self._repository = repository
        self._thread_binding_service = thread_binding_service
        self._session_manager = session_manager
        self._event_publisher = event_publisher
        self._storage = storage
        self._tree_service = tree_service
        self._finish_task_service = finish_task_service
        self._review_service = review_service
        self._metadata_service = WorkflowMetadataService(tree_service, finish_task_service)
        self._artifact_service = GitArtifactService(git_checkpoint_service)
        self._settlement_mismatch_count = 0

    def get_workflow_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        return _public_state(self._repository.read_state(project_id, node_id))

    def get_legacy_workflow_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        return legacy_workflow_state_view(self._repository.read_state(project_id, node_id))

    def get_active_execution_start_response(self, project_id: str, node_id: str) -> dict[str, Any] | None:
        state = self._repository.read_state(project_id, node_id)
        if state.phase != "executing":
            return None
        run_id = state.active_execution_run_id or state.latest_execution_run_id
        run = state.execution_runs.get(str(run_id or ""))
        return {
            "accepted": True,
            "threadId": run.thread_id if run is not None else state.execution_thread_id,
            "turnId": run.turn_id if run is not None else None,
            "executionRunId": run_id,
            "workflowState": _public_state(state),
        }

    def start_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        model: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "start_execution",
                "projectId": project_id,
                "nodeId": node_id,
                "model": model,
                "modelProvider": model_provider,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "start_execution", key, payload_hash)
        if replay is not None:
            return replay
        execution_run_id = new_id("exec_run")
        transition_start_execution(
            state,
            execution_run_id=execution_run_id,
            execution_thread_id=state.execution_thread_id,
        )

        metadata = self._metadata_service.load_execution_metadata(
            project_id,
            node_id,
            validate_finish_task=True,
        )
        prompt = build_execution_prompt(
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            task_context=metadata["taskContext"],
        )
        return self._start_execution_turn(
            project_id,
            node_id,
            action="start_execution",
            trigger_kind="finish_task",
            idempotency_key=key,
            payload_hash=payload_hash,
            prompt=prompt,
            start_sha=str(metadata["initialSha"]),
            workspace_root=metadata["workspaceRoot"],
            model=model,
            model_provider=model_provider,
            summary_seed=None,
            execution_run_id=execution_run_id,
        )

    def complete_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        candidate_workspace_hash: str | None = None,
        execution_run_id: str | None = None,
        execution_turn_id: str | None = None,
        head_commit_sha: str | None = None,
        summary_text: str | None = None,
    ) -> dict[str, Any]:
        state = self._repository.read_state(project_id, node_id)
        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        resolved_hash = candidate_workspace_hash or self._artifact_service.compute_workspace_hash(metadata["workspaceRoot"])
        resolved_run_id = execution_run_id or state.active_execution_run_id or state.latest_execution_run_id
        next_state = transition_complete_execution(
            state,
            candidate_workspace_hash=resolved_hash,
            execution_run_id=resolved_run_id,
            execution_turn_id=execution_turn_id,
            head_commit_sha=head_commit_sha,
            summary_text=summary_text,
        )
        next_state = _update_execution_run(
            next_state,
            run_id=resolved_run_id,
            status="completed",
            candidate_workspace_hash=resolved_hash,
            summary_text=summary_text,
            completed_at=utc_now_iso(),
        )
        persisted = self._repository.write_state(project_id, node_id, next_state)
        self._publish_state_changed(persisted, action="start_execution", reason="execution_completed")
        return {"workflowState": _public_state(persisted)}

    def mark_done_from_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "mark_done_from_execution",
                "projectId": project_id,
                "nodeId": node_id,
                "expectedWorkspaceHash": expected_workspace_hash,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "mark_done_from_execution", key, payload_hash)
        if replay is not None:
            return replay
        transition_mark_done_from_execution(
            state,
            expected_workspace_hash=expected_workspace_hash,
        )

        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        self._require_workspace_hash(metadata["workspaceRoot"], expected_workspace_hash)
        decision = state.current_execution_decision
        run_id = decision.source_execution_run_id if decision else None
        summary_text = self._resolve_execution_summary_text(state, run_id)
        self._upsert_handoff_summary_best_effort(
            project_id=project_id,
            node_id=node_id,
            workspace_root=metadata["workspaceRoot"],
            snapshot=metadata["snapshot"],
            node=metadata["node"],
            summary_text=summary_text,
        )
        commit_result = self._artifact_service.commit_workspace(
            workspace_root=metadata["workspaceRoot"],
            hierarchical_number=str(metadata["node"].get("hierarchical_number") or "1"),
            title=str(metadata["node"].get("title") or "task").strip() or "task",
            verb="complete",
        )
        next_state = transition_mark_done_from_execution(
            state,
            expected_workspace_hash=expected_workspace_hash,
            accepted_sha=commit_result["headSha"],
        )
        next_state = next_state.model_copy(
            deep=True,
            update={
                "head_commit_sha": commit_result["headSha"],
                "accepted_sha": commit_result["headSha"],
                "execution_runs": _execution_runs_with_decision(
                    next_state,
                    run_id=run_id,
                    committed_head_sha=commit_result["headSha"],
                    decision="accepted",
                ),
            },
        )
        response = self._write_action_state(
            project_id,
            node_id,
            next_state,
            action="mark_done_from_execution",
            idempotency_key=key,
            payload_hash=payload_hash,
            response_builder=lambda projected: {"workflowState": _public_state(projected)},
        )
        self._complete_node_progression(
            project_id,
            node_id,
            accepted_sha=commit_result["headSha"],
            summary_text=summary_text,
        )
        return response

    def start_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
        model: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "start_audit",
                "projectId": project_id,
                "nodeId": node_id,
                "expectedWorkspaceHash": expected_workspace_hash,
                "model": model,
                "modelProvider": model_provider,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "start_audit", key, payload_hash)
        if replay is not None:
            return replay
        audit_run_id = new_id("audit_run")
        transition_start_audit(
            state,
            audit_run_id=audit_run_id,
            audit_thread_id=state.audit_thread_id,
            expected_workspace_hash=expected_workspace_hash,
        )

        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        self._require_workspace_hash(metadata["workspaceRoot"], expected_workspace_hash)
        commit_result = self._artifact_service.commit_workspace(
            workspace_root=metadata["workspaceRoot"],
            hierarchical_number=str(metadata["node"].get("hierarchical_number") or "1"),
            title=str(metadata["node"].get("title") or "task").strip() or "task",
            verb="review",
        )
        review_commit_sha = commit_result["headSha"]
        binding = self._thread_binding_service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="audit",
            idempotency_key=f"{key}:audit-thread",
            model=model,
            model_provider=model_provider,
        )
        thread_id = _binding_thread_id(binding)
        latest_state = self._repository.read_state(project_id, node_id)
        next_state = transition_start_audit(
            latest_state,
            audit_run_id=audit_run_id,
            audit_thread_id=thread_id,
            expected_workspace_hash=expected_workspace_hash,
        )
        prompt = self._metadata_service.build_audit_review_prompt(
            node=metadata["node"],
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            review_commit_sha=review_commit_sha,
        )
        turn_id = self._start_session_turn(
            thread_id=thread_id,
            client_action_id=f"{key}:audit-turn",
            text=prompt,
            cwd=metadata["workspaceRoot"],
            model=model,
        )
        source_execution_run_id = (
            latest_state.current_execution_decision.source_execution_run_id
            if latest_state.current_execution_decision is not None
            else None
        )
        audit_runs = dict(next_state.audit_runs)
        audit_runs[audit_run_id] = AuditRunV2(
            runId=audit_run_id,
            threadId=thread_id,
            turnId=turn_id,
            sourceExecutionRunId=source_execution_run_id,
            clientRequestId=key,
            reviewCommitSha=review_commit_sha,
            status="running",
            startedAt=utc_now_iso(),
        )
        next_state = next_state.model_copy(
            deep=True,
            update={
                "audit_runs": audit_runs,
                "head_commit_sha": review_commit_sha,
                "execution_runs": _execution_runs_with_decision(
                    next_state,
                    run_id=source_execution_run_id,
                    committed_head_sha=review_commit_sha,
                    decision="sent_to_review",
                ),
            },
        )
        logger.info(
            "workflow_v2 start audit turn accepted",
            extra={
                "idempotencyKey": key,
                "projectId": project_id,
                "nodeId": node_id,
                "role": "audit",
                "threadId": thread_id,
                "turnId": turn_id,
                "auditRunId": audit_run_id,
                "executionRunId": source_execution_run_id,
            },
        )
        return self._write_action_state(
            project_id,
            node_id,
            next_state,
            action="start_audit",
            idempotency_key=key,
            payload_hash=payload_hash,
            response_builder=lambda projected: {
                "accepted": True,
                "auditRunId": audit_run_id,
                "reviewCycleId": audit_run_id,
                "threadId": thread_id,
                "reviewThreadId": thread_id,
                "turnId": turn_id,
                "reviewCommitSha": review_commit_sha,
                "workflowState": _public_state(projected),
            },
        )

    def complete_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        review_commit_sha: str,
        audit_run_id: str | None = None,
        final_review_text: str | None = None,
        review_disposition: str | None = None,
    ) -> dict[str, Any]:
        state = self._repository.read_state(project_id, node_id)
        next_state = transition_complete_audit(
            state,
            review_commit_sha=review_commit_sha,
            audit_run_id=audit_run_id,
            final_review_text=final_review_text,
            review_disposition=review_disposition,
        )
        resolved_run_id = audit_run_id or state.active_audit_run_id or state.latest_audit_run_id
        next_state = _update_audit_run(
            next_state,
            run_id=resolved_run_id,
            status="completed",
            review_commit_sha=review_commit_sha,
            final_review_text=final_review_text,
            review_disposition=review_disposition,
            completed_at=utc_now_iso(),
        )
        persisted = self._repository.write_state(project_id, node_id, next_state)
        self._publish_state_changed(persisted, action="review_in_audit", reason="audit_completed")
        return {"workflowState": _public_state(persisted)}

    def accept_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "accept_audit",
                "projectId": project_id,
                "nodeId": node_id,
                "expectedReviewCommitSha": expected_review_commit_sha,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "accept_audit", key, payload_hash)
        if replay is not None:
            return replay
        transition_mark_done_from_audit(
            state,
            expected_review_commit_sha=expected_review_commit_sha,
        )

        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        self._require_head_sha(metadata["workspaceRoot"], expected_review_commit_sha)
        run_id = self._resolve_execution_run_id_for_audit_accept(state)
        summary_text = self._resolve_execution_summary_text(state, run_id)
        next_state = transition_mark_done_from_audit(
            state,
            expected_review_commit_sha=expected_review_commit_sha,
        )
        response = self._write_action_state(
            project_id,
            node_id,
            next_state,
            action="accept_audit",
            idempotency_key=key,
            payload_hash=payload_hash,
            response_builder=lambda projected: {"workflowState": _public_state(projected)},
        )
        self._complete_node_progression(
            project_id,
            node_id,
            accepted_sha=expected_review_commit_sha,
            summary_text=summary_text,
        )
        return response

    def request_improvements(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
        model: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "request_improvements",
                "projectId": project_id,
                "nodeId": node_id,
                "expectedReviewCommitSha": expected_review_commit_sha,
                "model": model,
                "modelProvider": model_provider,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "request_improvements", key, payload_hash)
        if replay is not None:
            return replay
        decision = state.current_audit_decision
        review_text = str(decision.final_review_text if decision is not None and decision.final_review_text else "").strip()
        if not review_text:
            raise WorkflowActionNotAllowedError(
                "improve_in_execution",
                state.phase,
                allowed_actions=derive_allowed_actions(state),
                message="No completed audit review text is available for improvement.",
            )
        execution_run_id = new_id("exec_run")
        transition_improve_execution(
            state,
            expected_review_commit_sha=expected_review_commit_sha,
            execution_run_id=execution_run_id,
            execution_thread_id=state.execution_thread_id,
        )
        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        self._require_head_sha(metadata["workspaceRoot"], expected_review_commit_sha)
        prompt = self._metadata_service.build_improve_prompt(
            spec_content=metadata["specContent"],
            frame_content=metadata["frameContent"],
            task_context=metadata["taskContext"],
            review_text=review_text,
        )
        return self._start_execution_turn(
            project_id,
            node_id,
            action="request_improvements",
            trigger_kind="improve_from_review",
            idempotency_key=key,
            payload_hash=payload_hash,
            prompt=prompt,
            start_sha=expected_review_commit_sha,
            workspace_root=metadata["workspaceRoot"],
            model=model,
            model_provider=model_provider,
            summary_seed=review_text,
            execution_run_id=execution_run_id,
        )

    def start_package_review(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        model: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any]:
        key = _require_key(idempotency_key)
        payload_hash = _payload_hash(
            {
                "action": "start_package_review",
                "projectId": project_id,
                "nodeId": node_id,
                "model": model,
                "modelProvider": model_provider,
            }
        )
        state = self._repository.read_state(project_id, node_id)
        replay = self._resolve_idempotent(state, "start_package_review", key, payload_hash)
        if replay is not None:
            return replay
        transition_start_package_review(
            state,
            package_review_thread_id=None,
        )

        binding = self._thread_binding_service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="package_review",
            idempotency_key=f"{key}:package-review-thread",
            model=model,
            model_provider=model_provider,
        )
        thread_id = _binding_thread_id(binding)
        latest_state = self._repository.read_state(project_id, node_id)
        next_state = transition_start_package_review(
            latest_state,
            package_review_thread_id=thread_id,
        )
        metadata = self._metadata_service.load_execution_metadata(project_id, node_id)
        prompt = build_package_review_prompt(
            self._storage,
            project_id,
            node_id,
            "Review this completed package. Summarize readiness, blockers, and follow-up actions.",
        )
        turn_id = self._start_session_turn(
            thread_id=thread_id,
            client_action_id=f"{key}:package-review-turn",
            text=prompt,
            cwd=metadata["workspaceRoot"],
            model=model,
        )
        logger.info(
            "workflow_v2 start package review turn accepted",
            extra={
                "idempotencyKey": key,
                "projectId": project_id,
                "nodeId": node_id,
                "role": "package_review",
                "threadId": thread_id,
                "turnId": turn_id,
            },
        )
        return self._write_action_state(
            project_id,
            node_id,
            next_state,
            action="start_package_review",
            idempotency_key=key,
            payload_hash=payload_hash,
            response_builder=lambda projected: {
                "accepted": True,
                "threadId": thread_id,
                "turnId": turn_id,
                "workflowState": _public_state(projected),
            },
        )

    def handle_session_event(self, event: dict[str, Any]) -> None:
        if str(event.get("method") or "") != "turn/completed":
            return
        thread_id = str(event.get("threadId") or "").strip()
        turn_id = str(event.get("turnId") or "").strip()
        event_seq = event.get("eventSeq")
        params = event.get("params")
        turn = params.get("turn") if isinstance(params, dict) else None
        if isinstance(turn, dict):
            turn_id = str(turn.get("id") or turn_id).strip()
            status = str(turn.get("status") or "").strip()
        else:
            turn = None
            status = ""
        if not thread_id or not turn_id:
            return
        self.settle_terminal_turn(
            thread_id=thread_id,
            turn_id=turn_id,
            status=status,
            turn=turn,
            event_seq=event_seq,
        )

    def settle_terminal_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        status: str | None = None,
        turn: dict[str, Any] | None = None,
        event_seq: int | None = None,
    ) -> dict[str, Any] | None:
        terminal_status = str(status or "").strip() or str((turn or {}).get("status") or "").strip()
        if terminal_status and terminal_status != "completed":
            logger.info(
                "Workflow V2 terminal turn settlement skipped for non-completed turn",
                extra={"threadId": thread_id, "turnId": turn_id, "status": terminal_status},
            )
            return None
        match = self._find_active_run_by_turn(thread_id=thread_id, turn_id=turn_id)
        if match is None:
            self._settlement_mismatch_count += 1
            logger.warning(
                "workflow_v2 settlement mismatch: no active run matched terminal turn",
                extra={
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "eventSeq": event_seq,
                    "settlementMismatchCount": self._settlement_mismatch_count,
                },
            )
            return None
        kind, project_id, node_id, state = match
        logger.info(
            "workflow_v2 settle terminal turn",
            extra={
                "projectId": project_id,
                "nodeId": node_id,
                "threadId": thread_id,
                "turnId": turn_id,
                "eventSeq": event_seq,
                "activeExecutionRunId": state.active_execution_run_id,
                "activeAuditRunId": state.active_audit_run_id,
            },
        )
        text = _extract_turn_text(turn)
        if kind == "execution":
            run_id = state.active_execution_run_id or state.latest_execution_run_id
            return self.complete_execution(
                project_id,
                node_id,
                execution_run_id=run_id,
                execution_turn_id=turn_id,
                summary_text=text,
            )
        audit_run_id = state.active_audit_run_id or state.latest_audit_run_id
        audit_run = state.audit_runs.get(str(audit_run_id or ""))
        review_commit_sha = (
            audit_run.review_commit_sha
            if audit_run is not None and audit_run.review_commit_sha
            else state.head_commit_sha
        )
        if not review_commit_sha:
            return None
        return self.complete_audit(
            project_id,
            node_id,
            audit_run_id=audit_run_id,
            review_commit_sha=review_commit_sha,
            final_review_text=text,
        )

    def _start_execution_turn(
        self,
        project_id: str,
        node_id: str,
        *,
        action: str,
        trigger_kind: str,
        idempotency_key: str,
        payload_hash: str,
        prompt: str,
        start_sha: str,
        workspace_root: str | None,
        model: str | None,
        model_provider: str | None,
        summary_seed: str | None,
        execution_run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = execution_run_id or new_id("exec_run")
        validation_state = self._repository.read_state(project_id, node_id)
        if action == "request_improvements":
            transition_improve_execution(
                validation_state,
                expected_review_commit_sha=start_sha,
                execution_run_id=run_id,
                execution_thread_id=validation_state.execution_thread_id,
            )
        else:
            transition_start_execution(
                validation_state,
                execution_run_id=run_id,
                execution_thread_id=validation_state.execution_thread_id,
            )
        binding = self._thread_binding_service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="execution",
            idempotency_key=f"{idempotency_key}:execution-thread",
            model=model,
            model_provider=model_provider,
        )
        thread_id = _binding_thread_id(binding)
        latest_state = self._repository.read_state(project_id, node_id)
        if action == "request_improvements":
            next_state = transition_improve_execution(
                latest_state,
                expected_review_commit_sha=start_sha,
                execution_run_id=run_id,
                execution_thread_id=thread_id,
            )
        else:
            next_state = transition_start_execution(
                latest_state,
                execution_run_id=run_id,
                execution_thread_id=thread_id,
            )
        turn_id = self._start_session_turn(
            thread_id=thread_id,
            client_action_id=f"{idempotency_key}:execution-turn",
            text=prompt,
            cwd=workspace_root,
            model=model,
        )
        execution_runs = dict(next_state.execution_runs)
        execution_runs[run_id] = ExecutionRunV2(
            runId=run_id,
            threadId=thread_id,
            turnId=turn_id,
            clientRequestId=idempotency_key,
            triggerKind=trigger_kind,
            startSha=start_sha,
            status="running",
            decision="pending",
            summaryText=summary_seed,
            startedAt=utc_now_iso(),
        )
        next_state = next_state.model_copy(
            deep=True,
            update={
                "base_commit_sha": start_sha,
                "execution_runs": execution_runs,
            },
        )
        logger.info(
            "workflow_v2 start execution turn accepted",
            extra={
                "idempotencyKey": idempotency_key,
                "projectId": project_id,
                "nodeId": node_id,
                "role": "execution",
                "threadId": thread_id,
                "turnId": turn_id,
                "executionRunId": run_id,
            },
        )
        return self._write_action_state(
            project_id,
            node_id,
            next_state,
            action=action,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            response_builder=lambda projected: {
                "accepted": True,
                "threadId": thread_id,
                "turnId": turn_id,
                "executionRunId": run_id,
                "workflowState": _public_state(projected),
            },
        )

    def _find_active_run_by_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
    ) -> tuple[str, str, str, NodeWorkflowStateV2] | None:
        target_thread_id = str(thread_id or "").strip()
        target_turn_id = str(turn_id or "").strip()
        if not target_thread_id or not target_turn_id:
            return None
        for entry in self._storage.workspace_store.list_entries():
            project_id = str(entry.get("project_id") or "").strip()
            folder_path = str(entry.get("folder_path") or "").strip()
            if not project_id or not folder_path:
                continue
            workflow_dir = Path(folder_path).expanduser().resolve() / ".planningtree" / "workflow_core_v2"
            if not workflow_dir.is_dir():
                continue
            for state_file in workflow_dir.glob("*.json"):
                node_id = state_file.stem
                state = self._repository.read_state(project_id, node_id)
                active_execution_run = state.execution_runs.get(str(state.active_execution_run_id or ""))
                if (
                    state.phase == "executing"
                    and active_execution_run is not None
                    and active_execution_run.thread_id == target_thread_id
                    and active_execution_run.turn_id == target_turn_id
                ):
                    return ("execution", project_id, node_id, state)
                active_audit_run = state.audit_runs.get(str(state.active_audit_run_id or ""))
                if (
                    state.phase == "audit_running"
                    and active_audit_run is not None
                    and active_audit_run.thread_id == target_thread_id
                    and active_audit_run.turn_id == target_turn_id
                ):
                    return ("audit", project_id, node_id, state)
        return None

    def _require_workspace_hash(self, workspace_root: str | None, expected_workspace_hash: str) -> str:
        try:
            return self._artifact_service.require_workspace_hash(workspace_root, expected_workspace_hash)
        except AppError as exc:
            raise WorkflowArtifactVersionConflictError(
                exc.message,
                details={"expectedWorkspaceHash": expected_workspace_hash},
            ) from exc

    def _require_head_sha(self, workspace_root: str | None, expected_head_sha: str) -> str:
        try:
            return self._artifact_service.require_head_sha(workspace_root, expected_head_sha)
        except AppError as exc:
            raise WorkflowArtifactVersionConflictError(
                exc.message,
                details={"expectedReviewCommitSha": expected_head_sha},
            ) from exc

    def _start_session_turn(
        self,
        *,
        thread_id: str,
        client_action_id: str,
        text: str,
        cwd: str | None,
        model: str | None,
    ) -> str:
        payload: dict[str, Any] = {
            "clientActionId": client_action_id,
            "input": [{"type": "text", "text": text}],
        }
        if cwd:
            payload["cwd"] = cwd
        if model:
            payload["model"] = model
        response = self._session_manager.turn_start(thread_id=thread_id, payload=payload)
        turn = response.get("turn") if isinstance(response, dict) else None
        turn_id = str(turn.get("id") or "" if isinstance(turn, dict) else "").strip()
        if not turn_id:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="turn/start response missing turnId (provider contract violation).",
                status_code=502,
                details={
                    "threadId": thread_id,
                    "clientActionId": client_action_id,
                    "providerMethod": "turn/start",
                },
            )
        return turn_id

    def _resolve_idempotent(
        self,
        state: NodeWorkflowStateV2,
        action: str,
        idempotency_key: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        record = state.idempotency_records.get(_record_key(action, idempotency_key))
        if record is None:
            return None
        if record.get("payloadHash") != payload_hash:
            raise WorkflowIdempotencyConflictError(idempotency_key)
        response = record.get("response")
        return copy.deepcopy(response) if isinstance(response, dict) else None

    def _write_action_state(
        self,
        project_id: str,
        node_id: str,
        next_state: NodeWorkflowStateV2,
        *,
        action: str,
        idempotency_key: str,
        payload_hash: str,
        response_builder: Callable[[NodeWorkflowStateV2], dict[str, Any]],
    ) -> dict[str, Any]:
        projected = next_state.model_copy(deep=True, update={"state_version": next_state.state_version + 1})
        response = response_builder(projected)
        records = copy.deepcopy(next_state.idempotency_records)
        records[_record_key(action, idempotency_key)] = {
            "action": action,
            "payloadHash": payload_hash,
            "response": copy.deepcopy(response),
        }
        persisted = self._repository.write_state(
            project_id,
            node_id,
            next_state.model_copy(deep=True, update={"idempotency_records": records}),
        )
        public_action = _public_action(action)
        self._publish_action_completed(persisted, action=public_action, reason=action)
        self._publish_state_changed(persisted, action=public_action, reason=action)
        return response_builder(persisted)

    def _publish_state_changed(
        self,
        state: NodeWorkflowStateV2,
        *,
        action: WorkflowAction | None,
        reason: str,
    ) -> None:
        if self._event_publisher is not None:
            self._event_publisher.publish_state_changed(
                state,
                details={"reason": reason, **({"action": action} if action else {})},
            )

    def _publish_action_completed(
        self,
        state: NodeWorkflowStateV2,
        *,
        action: WorkflowAction | None,
        reason: str,
    ) -> None:
        if self._event_publisher is not None and action is not None:
            self._event_publisher.publish_action_completed(
                state,
                action=action,
                details={"reason": reason},
            )

    def _resolve_execution_summary_text(self, state: NodeWorkflowStateV2, run_id: str | None) -> str:
        target = str(run_id or "").strip()
        if not target:
            return _HANDOFF_SUMMARY_PLACEHOLDER
        run = state.execution_runs.get(target)
        if run is None:
            return _HANDOFF_SUMMARY_PLACEHOLDER
        return str(run.summary_text or "").strip() or _HANDOFF_SUMMARY_PLACEHOLDER

    def _resolve_execution_run_id_for_audit_accept(self, state: NodeWorkflowStateV2) -> str | None:
        decision = state.current_audit_decision
        audit_run_id = decision.source_audit_run_id if decision is not None else state.latest_audit_run_id
        audit_run = state.audit_runs.get(str(audit_run_id or ""))
        if audit_run is not None and audit_run.source_execution_run_id:
            return audit_run.source_execution_run_id
        return state.latest_execution_run_id

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
                pass

        if activated_sibling_id and activated_review_node_id and activated_workspace_root and self._review_service is not None:
            self._review_service._bootstrap_child_audit_best_effort(
                project_id,
                activated_review_node_id,
                activated_sibling_id,
                activated_workspace_root,
            )

    def _upsert_handoff_summary_best_effort(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
        snapshot: Any,
        node: Any,
        summary_text: str,
    ) -> None:
        # Keep Phase 5 focused on workflow ownership; legacy handoff docs are best effort.
        try:
            root = str(workspace_root or "").strip()
            if not root:
                return
            target = Path(root).expanduser().resolve() / ".planningtree" / "handoff.md"
            existing = target.read_text(encoding="utf-8") if target.exists() else "# Implementation Handoff\n\n"
            label = f"{node.get('hierarchical_number') or ''} {node.get('title') or 'Task'}".strip()
            block = (
                f"<!-- PT_HANDOFF_NODE:{node_id} -->\n"
                f"## {label}\n\n"
                f"{str(summary_text or '').strip() or _HANDOFF_SUMMARY_PLACEHOLDER}\n"
                f"<!-- /PT_HANDOFF_NODE:{node_id} -->\n"
            )
            start = existing.find(f"<!-- PT_HANDOFF_NODE:{node_id} -->")
            end = existing.find(f"<!-- /PT_HANDOFF_NODE:{node_id} -->")
            if start >= 0 and end >= start:
                end += len(f"<!-- /PT_HANDOFF_NODE:{node_id} -->")
                updated = f"{existing[:start]}{block}{existing[end:].lstrip()}"
            else:
                separator = "" if existing.endswith("\n") else "\n"
                updated = f"{existing}{separator}{block}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(updated, encoding="utf-8")
        except Exception:
            return


def _public_state(state: NodeWorkflowStateV2) -> dict[str, Any]:
    return workflow_state_to_response(
        state,
        allowed_actions=derive_allowed_actions(state),
    ).to_public_dict()


def _binding_thread_id(response: dict[str, Any]) -> str:
    binding = response.get("binding")
    raw_thread_id = binding.get("threadId") if isinstance(binding, dict) else None
    thread_id = str(raw_thread_id or "").strip()
    if not thread_id:
        raise WorkflowActionNotAllowedError("ensure_thread", "unknown", message="Workflow thread binding did not return a thread id.")
    return thread_id


def _extract_turn_text(turn: dict[str, Any] | None) -> str | None:
    if not isinstance(turn, dict):
        return None
    chunks: list[str] = []
    for item in turn.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("kind") or "").strip()
        if item_type not in {"agentMessage", "message", "assistantMessage"}:
            continue
        text = item.get("text") or item.get("content")
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks) or None


def _require_key(idempotency_key: str) -> str:
    key = str(idempotency_key or "").strip()
    if not key:
        raise WorkflowActionNotAllowedError("idempotent_action", "unknown", message="idempotencyKey is required.")
    return key


def _record_key(action: str, idempotency_key: str) -> str:
    return f"{action}:{idempotency_key}"


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _public_action(action: str) -> WorkflowAction | None:
    mapping: dict[str, WorkflowAction] = {
        "start_execution": "start_execution",
        "mark_done_from_execution": "mark_done_from_execution",
        "start_audit": "review_in_audit",
        "accept_audit": "mark_done_from_audit",
        "request_improvements": "improve_in_execution",
        "start_package_review": "start_package_review",
    }
    return mapping.get(action)


def _update_execution_run(
    state: NodeWorkflowStateV2,
    *,
    run_id: str | None,
    status: str,
    candidate_workspace_hash: str | None = None,
    summary_text: str | None = None,
    completed_at: str | None = None,
) -> NodeWorkflowStateV2:
    if not run_id:
        return state
    runs = dict(state.execution_runs)
    existing = runs.get(run_id)
    if existing is None:
        existing = ExecutionRunV2(runId=run_id)
    runs[run_id] = existing.model_copy(
        deep=True,
        update={
            "status": status,
            "candidate_workspace_hash": candidate_workspace_hash or existing.candidate_workspace_hash,
            "summary_text": summary_text if summary_text is not None else existing.summary_text,
            "completed_at": completed_at or existing.completed_at,
        },
    )
    return state.model_copy(deep=True, update={"execution_runs": runs})


def _execution_runs_with_decision(
    state: NodeWorkflowStateV2,
    *,
    run_id: str | None,
    committed_head_sha: str,
    decision: str,
) -> dict[str, ExecutionRunV2]:
    runs = dict(state.execution_runs)
    if run_id and run_id in runs:
        runs[run_id] = runs[run_id].model_copy(
            deep=True,
            update={
                "committed_head_sha": committed_head_sha,
                "decision": decision,
                "decided_at": utc_now_iso(),
            },
        )
    return runs


def _update_audit_run(
    state: NodeWorkflowStateV2,
    *,
    run_id: str | None,
    status: str,
    review_commit_sha: str | None = None,
    final_review_text: str | None = None,
    review_disposition: str | None = None,
    completed_at: str | None = None,
) -> NodeWorkflowStateV2:
    if not run_id:
        return state
    runs = dict(state.audit_runs)
    existing = runs.get(run_id)
    if existing is None:
        existing = AuditRunV2(runId=run_id)
    runs[run_id] = existing.model_copy(
        deep=True,
        update={
            "status": status,
            "review_commit_sha": review_commit_sha or existing.review_commit_sha,
            "final_review_text": final_review_text if final_review_text is not None else existing.final_review_text,
            "review_disposition": review_disposition if review_disposition is not None else existing.review_disposition,
            "completed_at": completed_at or existing.completed_at,
        },
    )
    return state.model_copy(deep=True, update={"audit_runs": runs})


def legacy_workflow_state_view(state: NodeWorkflowStateV2) -> dict[str, Any]:
    legacy_phase = _legacy_phase(state.phase)
    execution_decision = (
        state.current_execution_decision.model_dump(by_alias=True, mode="json")
        if state.current_execution_decision is not None
        else None
    )
    audit_decision = _legacy_audit_decision(state)
    return {
        "nodeId": state.node_id,
        "workflowPhase": legacy_phase,
        "askThreadId": state.ask_thread_id,
        "executionThreadId": state.execution_thread_id,
        "auditLineageThreadId": state.audit_thread_id,
        "reviewThreadId": state.audit_thread_id,
        "activeExecutionRunId": state.active_execution_run_id,
        "latestExecutionRunId": state.latest_execution_run_id,
        "activeReviewCycleId": state.active_audit_run_id,
        "latestReviewCycleId": state.latest_audit_run_id,
        "currentExecutionDecision": execution_decision,
        "currentAuditDecision": audit_decision,
        "acceptedSha": state.accepted_sha,
        "runtimeBlock": (
            {"kind": "workflow_v2_blocked", "message": state.blocked_reason or ""}
            if state.phase == "blocked"
            else copy.deepcopy(state.last_error)
        ),
        "canSendExecutionMessage": legacy_phase == "execution_decision_pending" and execution_decision is not None,
        "canReviewInAudit": legacy_phase == "execution_decision_pending" and execution_decision is not None,
        "canImproveInExecution": legacy_phase == "audit_decision_pending" and audit_decision is not None,
        "canMarkDoneFromExecution": legacy_phase == "execution_decision_pending" and execution_decision is not None,
        "canMarkDoneFromAudit": legacy_phase == "audit_decision_pending" and audit_decision is not None,
    }


def _legacy_phase(phase: WorkflowPhase) -> str:
    mapping = {
        "planning": "idle",
        "ready_for_execution": "idle",
        "executing": "execution_running",
        "execution_completed": "execution_decision_pending",
        "audit_running": "audit_running",
        "review_pending": "audit_decision_pending",
        "audit_needs_changes": "audit_decision_pending",
        "audit_accepted": "audit_decision_pending",
        "done": "done",
        "blocked": "failed",
    }
    return mapping[phase]


def _legacy_audit_decision(state: NodeWorkflowStateV2) -> dict[str, Any] | None:
    decision = state.current_audit_decision
    if decision is None:
        return None
    return {
        "status": decision.status,
        "sourceReviewCycleId": decision.source_audit_run_id,
        "reviewCommitSha": decision.review_commit_sha,
        "finalReviewText": decision.final_review_text,
        "reviewDisposition": decision.review_disposition,
        "createdAt": decision.created_at,
    }
