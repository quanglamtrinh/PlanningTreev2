from __future__ import annotations

import copy
from typing import Any

from backend.business.workflow_v2.errors import (
    WorkflowActionNotAllowedError,
    WorkflowArtifactVersionConflictError,
)
from backend.business.workflow_v2.models import (
    AuditDecisionV2,
    ExecutionDecisionV2,
    NodeWorkflowStateV2,
    WorkflowAction,
    utc_now_iso,
)


def derive_allowed_actions(state: NodeWorkflowStateV2) -> list[WorkflowAction]:
    if state.phase == "ready_for_execution":
        return ["start_execution"]
    if state.phase == "execution_completed" and state.current_execution_decision is not None:
        return ["review_in_audit", "mark_done_from_execution"]
    if state.phase in {"review_pending", "audit_needs_changes"} and state.current_audit_decision is not None:
        return ["improve_in_execution", "mark_done_from_audit"]
    if state.phase == "done" and state.package_review_thread_id is None:
        return ["start_package_review"]
    return []


def start_execution(
    state: NodeWorkflowStateV2,
    *,
    execution_run_id: str,
    execution_thread_id: str | None = None,
) -> NodeWorkflowStateV2:
    _require_action(state, "start_execution")
    return state.model_copy(
        deep=True,
        update={
            "phase": "executing",
            "execution_thread_id": execution_thread_id or state.execution_thread_id,
            "active_execution_run_id": execution_run_id,
            "latest_execution_run_id": execution_run_id,
            "current_execution_decision": None,
            "current_audit_decision": None,
            "blocked_reason": None,
            "last_error": None,
        },
    )


def complete_execution(
    state: NodeWorkflowStateV2,
    *,
    candidate_workspace_hash: str,
    execution_run_id: str | None = None,
    execution_turn_id: str | None = None,
    head_commit_sha: str | None = None,
    summary_text: str | None = None,
) -> NodeWorkflowStateV2:
    if state.phase != "executing":
        raise WorkflowActionNotAllowedError(
            "complete_execution",
            state.phase,
            allowed_actions=derive_allowed_actions(state),
        )
    resolved_run_id = execution_run_id or state.active_execution_run_id or state.latest_execution_run_id
    decision = ExecutionDecisionV2(
        sourceExecutionRunId=resolved_run_id,
        executionTurnId=execution_turn_id,
        candidateWorkspaceHash=candidate_workspace_hash,
        summaryText=summary_text,
        createdAt=utc_now_iso(),
    )
    return state.model_copy(
        deep=True,
        update={
            "phase": "execution_completed",
            "active_execution_run_id": None,
            "latest_execution_run_id": resolved_run_id,
            "current_execution_decision": decision,
            "workspace_hash": candidate_workspace_hash,
            "head_commit_sha": head_commit_sha or state.head_commit_sha,
        },
    )


def mark_done_from_execution(
    state: NodeWorkflowStateV2,
    *,
    expected_workspace_hash: str,
    accepted_sha: str | None = None,
) -> NodeWorkflowStateV2:
    _require_action(state, "mark_done_from_execution")
    decision = state.current_execution_decision
    actual_hash = decision.candidate_workspace_hash if decision else None
    if actual_hash != expected_workspace_hash:
        raise WorkflowArtifactVersionConflictError(
            "Workspace hash does not match the current execution decision.",
            details={"expectedWorkspaceHash": expected_workspace_hash, "actualWorkspaceHash": actual_hash},
        )
    return state.model_copy(
        deep=True,
        update={
            "phase": "done",
            "active_execution_run_id": None,
            "accepted_sha": accepted_sha or state.head_commit_sha or state.accepted_sha,
        },
    )


def start_audit(
    state: NodeWorkflowStateV2,
    *,
    audit_run_id: str,
    audit_thread_id: str | None = None,
    expected_workspace_hash: str,
) -> NodeWorkflowStateV2:
    _require_action(state, "review_in_audit")
    decision = state.current_execution_decision
    actual_hash = decision.candidate_workspace_hash if decision else None
    if actual_hash != expected_workspace_hash:
        raise WorkflowArtifactVersionConflictError(
            "Workspace hash does not match the current execution decision.",
            details={"expectedWorkspaceHash": expected_workspace_hash, "actualWorkspaceHash": actual_hash},
        )
    return state.model_copy(
        deep=True,
        update={
            "phase": "audit_running",
            "audit_thread_id": audit_thread_id or state.audit_thread_id,
            "active_audit_run_id": audit_run_id,
            "latest_audit_run_id": audit_run_id,
            "active_execution_run_id": None,
            "current_audit_decision": None,
        },
    )


def complete_audit(
    state: NodeWorkflowStateV2,
    *,
    review_commit_sha: str,
    audit_run_id: str | None = None,
    final_review_text: str | None = None,
    review_disposition: str | None = None,
) -> NodeWorkflowStateV2:
    if state.phase != "audit_running":
        raise WorkflowActionNotAllowedError(
            "complete_audit",
            state.phase,
            allowed_actions=derive_allowed_actions(state),
        )
    resolved_run_id = audit_run_id or state.active_audit_run_id or state.latest_audit_run_id
    decision = AuditDecisionV2(
        sourceAuditRunId=resolved_run_id,
        reviewCommitSha=review_commit_sha,
        finalReviewText=final_review_text,
        reviewDisposition=review_disposition,
        createdAt=utc_now_iso(),
    )
    return state.model_copy(
        deep=True,
        update={
            "phase": "review_pending",
            "active_audit_run_id": None,
            "latest_audit_run_id": resolved_run_id,
            "current_audit_decision": decision,
            "head_commit_sha": review_commit_sha,
        },
    )


def improve_execution(
    state: NodeWorkflowStateV2,
    *,
    expected_review_commit_sha: str,
    execution_run_id: str,
    execution_thread_id: str | None = None,
) -> NodeWorkflowStateV2:
    _require_action(state, "improve_in_execution")
    decision = state.current_audit_decision
    actual_sha = decision.review_commit_sha if decision else None
    if actual_sha != expected_review_commit_sha:
        raise WorkflowArtifactVersionConflictError(
            "Review commit SHA does not match the current audit decision.",
            details={"expectedReviewCommitSha": expected_review_commit_sha, "actualReviewCommitSha": actual_sha},
        )
    return state.model_copy(
        deep=True,
        update={
            "phase": "executing",
            "execution_thread_id": execution_thread_id or state.execution_thread_id,
            "active_execution_run_id": execution_run_id,
            "latest_execution_run_id": execution_run_id,
            "current_execution_decision": None,
            "current_audit_decision": None,
        },
    )


def mark_done_from_audit(
    state: NodeWorkflowStateV2,
    *,
    expected_review_commit_sha: str,
) -> NodeWorkflowStateV2:
    _require_action(state, "mark_done_from_audit")
    decision = state.current_audit_decision
    actual_sha = decision.review_commit_sha if decision else None
    if actual_sha != expected_review_commit_sha:
        raise WorkflowArtifactVersionConflictError(
            "Review commit SHA does not match the current audit decision.",
            details={"expectedReviewCommitSha": expected_review_commit_sha, "actualReviewCommitSha": actual_sha},
        )
    return state.model_copy(
        deep=True,
        update={
            "phase": "done",
            "active_audit_run_id": None,
            "accepted_sha": expected_review_commit_sha,
        },
    )


def start_package_review(
    state: NodeWorkflowStateV2,
    *,
    package_review_thread_id: str | None = None,
) -> NodeWorkflowStateV2:
    if (
        state.phase == "done"
        and state.package_review_thread_id is not None
        and state.package_review_thread_id == package_review_thread_id
    ):
        return state.model_copy(deep=True)
    _require_action(state, "start_package_review")
    return state.model_copy(
        deep=True,
        update={
            "package_review_thread_id": package_review_thread_id or state.package_review_thread_id,
        },
    )


def block(
    state: NodeWorkflowStateV2,
    *,
    reason: str,
    error: dict[str, Any] | None = None,
) -> NodeWorkflowStateV2:
    return state.model_copy(
        deep=True,
        update={
            "phase": "blocked",
            "blocked_reason": reason,
            "last_error": copy.deepcopy(error) if isinstance(error, dict) else None,
            "active_execution_run_id": None,
            "active_audit_run_id": None,
        },
    )


def _require_action(state: NodeWorkflowStateV2, action: WorkflowAction) -> None:
    allowed_actions = derive_allowed_actions(state)
    if action in allowed_actions:
        return
    raise WorkflowActionNotAllowedError(action, state.phase, allowed_actions=allowed_actions)
