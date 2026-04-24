from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowPhase = Literal[
    "planning",
    "ready_for_execution",
    "executing",
    "execution_completed",
    "review_pending",
    "audit_running",
    "audit_needs_changes",
    "audit_accepted",
    "done",
    "blocked",
]

ThreadRole = Literal["ask_planning", "execution", "audit", "package_review"]

WorkflowAction = Literal[
    "start_execution",
    "review_in_audit",
    "mark_done_from_execution",
    "improve_in_execution",
    "mark_done_from_audit",
    "start_package_review",
    "rebase_context",
]

WORKFLOW_SCHEMA_VERSION = 1

WORKFLOW_PHASES: tuple[str, ...] = (
    "planning",
    "ready_for_execution",
    "executing",
    "execution_completed",
    "review_pending",
    "audit_running",
    "audit_needs_changes",
    "audit_accepted",
    "done",
    "blocked",
)

THREAD_ROLES: tuple[str, ...] = ("ask_planning", "execution", "audit", "package_review")

WORKFLOW_ACTIONS: tuple[str, ...] = (
    "start_execution",
    "review_in_audit",
    "mark_done_from_execution",
    "improve_in_execution",
    "mark_done_from_audit",
    "start_package_review",
    "rebase_context",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SourceVersions(WorkflowModel):
    frame_version: int | None = Field(default=None, alias="frameVersion")
    spec_version: int | None = Field(default=None, alias="specVersion")
    split_manifest_version: int | None = Field(default=None, alias="splitManifestVersion")


class ExecutionDecisionV2(WorkflowModel):
    status: str = "current"
    source_execution_run_id: str | None = Field(default=None, alias="sourceExecutionRunId")
    execution_turn_id: str | None = Field(default=None, alias="executionTurnId")
    candidate_workspace_hash: str | None = Field(default=None, alias="candidateWorkspaceHash")
    summary_text: str | None = Field(default=None, alias="summaryText")
    created_at: str | None = Field(default=None, alias="createdAt")


class AuditDecisionV2(WorkflowModel):
    status: str = "current"
    source_audit_run_id: str | None = Field(default=None, alias="sourceAuditRunId")
    review_commit_sha: str | None = Field(default=None, alias="reviewCommitSha")
    final_review_text: str | None = Field(default=None, alias="finalReviewText")
    review_disposition: str | None = Field(default=None, alias="reviewDisposition")
    created_at: str | None = Field(default=None, alias="createdAt")


class ExecutionRunV2(WorkflowModel):
    run_id: str = Field(alias="runId")
    thread_id: str | None = Field(default=None, alias="threadId")
    turn_id: str | None = Field(default=None, alias="turnId")
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    trigger_kind: str | None = Field(default=None, alias="triggerKind")
    start_sha: str | None = Field(default=None, alias="startSha")
    status: str = "running"
    decision: str | None = None
    candidate_workspace_hash: str | None = Field(default=None, alias="candidateWorkspaceHash")
    committed_head_sha: str | None = Field(default=None, alias="committedHeadSha")
    summary_text: str | None = Field(default=None, alias="summaryText")
    error_message: str | None = Field(default=None, alias="errorMessage")
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    decided_at: str | None = Field(default=None, alias="decidedAt")


class AuditRunV2(WorkflowModel):
    run_id: str = Field(alias="runId")
    thread_id: str | None = Field(default=None, alias="threadId")
    turn_id: str | None = Field(default=None, alias="turnId")
    source_execution_run_id: str | None = Field(default=None, alias="sourceExecutionRunId")
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    review_commit_sha: str | None = Field(default=None, alias="reviewCommitSha")
    status: str = "running"
    review_disposition: str | None = Field(default=None, alias="reviewDisposition")
    final_review_text: str | None = Field(default=None, alias="finalReviewText")
    error_message: str | None = Field(default=None, alias="errorMessage")
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")


class ThreadBinding(WorkflowModel):
    project_id: str = Field(alias="projectId")
    node_id: str = Field(alias="nodeId")
    role: ThreadRole
    thread_id: str = Field(alias="threadId")
    created_from: str = Field(default="existing_thread", alias="createdFrom")
    source_versions: SourceVersions = Field(default_factory=SourceVersions, alias="sourceVersions")
    context_packet_hash: str | None = Field(default=None, alias="contextPacketHash")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class NodeWorkflowStateV2(BaseModel):
    schema_version: int = WORKFLOW_SCHEMA_VERSION
    state_version: int = 0
    project_id: str
    node_id: str
    phase: WorkflowPhase = "ready_for_execution"

    ask_thread_id: str | None = None
    execution_thread_id: str | None = None
    audit_thread_id: str | None = None
    package_review_thread_id: str | None = None

    active_execution_run_id: str | None = None
    latest_execution_run_id: str | None = None
    active_audit_run_id: str | None = None
    latest_audit_run_id: str | None = None

    current_execution_decision: ExecutionDecisionV2 | None = None
    current_audit_decision: AuditDecisionV2 | None = None
    execution_runs: dict[str, ExecutionRunV2] = Field(default_factory=dict)
    audit_runs: dict[str, AuditRunV2] = Field(default_factory=dict)

    workspace_hash: str | None = None
    base_commit_sha: str | None = None
    head_commit_sha: str | None = None
    accepted_sha: str | None = None

    frame_version: int | None = None
    spec_version: int | None = None
    split_manifest_version: int | None = None

    context_stale: bool = False
    context_stale_reason: str | None = None
    blocked_reason: str | None = None
    last_error: dict[str, Any] | None = None
    idempotency_records: dict[str, dict[str, Any]] = Field(default_factory=dict)
    thread_bindings: dict[str, ThreadBinding] = Field(default_factory=dict)

    created_at: str | None = None
    updated_at: str | None = None


class WorkflowThreadsResponseV2(WorkflowModel):
    ask_planning: str | None = Field(default=None, alias="askPlanning")
    execution: str | None = None
    audit: str | None = None
    package_review: str | None = Field(default=None, alias="packageReview")


class WorkflowDecisionsResponseV2(WorkflowModel):
    execution: ExecutionDecisionV2 | None = None
    audit: AuditDecisionV2 | None = None


class WorkflowContextResponseV2(WorkflowModel):
    frame_version: int | None = Field(default=None, alias="frameVersion")
    spec_version: int | None = Field(default=None, alias="specVersion")
    split_manifest_version: int | None = Field(default=None, alias="splitManifestVersion")
    stale: bool = False
    stale_reason: str | None = Field(default=None, alias="staleReason")


class WorkflowStateResponseV2(WorkflowModel):
    schema_version: int = Field(alias="schemaVersion")
    project_id: str = Field(alias="projectId")
    node_id: str = Field(alias="nodeId")
    phase: WorkflowPhase
    version: int
    threads: WorkflowThreadsResponseV2
    decisions: WorkflowDecisionsResponseV2
    context: WorkflowContextResponseV2
    allowed_actions: list[WorkflowAction] = Field(alias="allowedActions")

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def default_workflow_state(project_id: str, node_id: str) -> NodeWorkflowStateV2:
    now = utc_now_iso()
    return NodeWorkflowStateV2(
        project_id=project_id,
        node_id=node_id,
        phase="ready_for_execution",
        created_at=now,
        updated_at=now,
    )


def workflow_state_to_response(
    state: NodeWorkflowStateV2,
    *,
    allowed_actions: list[WorkflowAction],
) -> WorkflowStateResponseV2:
    return WorkflowStateResponseV2(
        schemaVersion=state.schema_version,
        projectId=state.project_id,
        nodeId=state.node_id,
        phase=state.phase,
        version=state.state_version,
        threads=WorkflowThreadsResponseV2(
            askPlanning=state.ask_thread_id,
            execution=state.execution_thread_id,
            audit=state.audit_thread_id,
            packageReview=state.package_review_thread_id,
        ),
        decisions=WorkflowDecisionsResponseV2(
            execution=copy.deepcopy(state.current_execution_decision),
            audit=copy.deepcopy(state.current_audit_decision),
        ),
        context=WorkflowContextResponseV2(
            frameVersion=state.frame_version,
            specVersion=state.spec_version,
            splitManifestVersion=state.split_manifest_version,
            stale=state.context_stale,
            staleReason=state.context_stale_reason,
        ),
        allowedActions=allowed_actions,
    )
