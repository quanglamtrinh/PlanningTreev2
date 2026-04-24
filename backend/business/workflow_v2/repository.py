from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.business.workflow_v2.models import (
    AuditDecisionV2,
    ExecutionDecisionV2,
    NodeWorkflowStateV2,
    WORKFLOW_SCHEMA_VERSION,
    default_workflow_state,
    utc_now_iso,
)
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.storage import Storage

LEGACY_PHASE_TO_V2: dict[str, str] = {
    "idle": "ready_for_execution",
    "execution_running": "executing",
    "execution_decision_pending": "execution_completed",
    "audit_running": "audit_running",
    "audit_decision_pending": "review_pending",
    "done": "done",
    "failed": "blocked",
}


class WorkflowStateRepositoryV2:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def canonical_path(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_core_v2" / f"{node_id}.json"

    def legacy_path(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_v2" / f"{node_id}.json"

    def read_state(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        with self._storage.project_lock(project_id):
            canonical_path = self.canonical_path(project_id, node_id)
            if canonical_path.exists():
                return self._normalize_canonical_state(
                    load_json(canonical_path, default={}),
                    project_id=project_id,
                    node_id=node_id,
                )
            legacy_path = self.legacy_path(project_id, node_id)
            if legacy_path.exists():
                return self.convert_legacy_state(
                    project_id,
                    node_id,
                    load_json(legacy_path, default={}),
                )
            return default_workflow_state(project_id, node_id)

    def write_state(
        self,
        project_id: str,
        node_id: str,
        state: NodeWorkflowStateV2,
    ) -> NodeWorkflowStateV2:
        with self._storage.project_lock(project_id):
            target = self.canonical_path(project_id, node_id)
            previous = None
            if target.exists():
                previous = self._normalize_canonical_state(
                    load_json(target, default={}),
                    project_id=project_id,
                    node_id=node_id,
                )
            now = utc_now_iso()
            next_state = state.model_copy(
                deep=True,
                update={
                    "schema_version": WORKFLOW_SCHEMA_VERSION,
                    "project_id": project_id,
                    "node_id": node_id,
                    "state_version": (previous.state_version + 1 if previous else state.state_version + 1),
                    "created_at": previous.created_at if previous else (state.created_at or now),
                    "updated_at": now,
                },
            )
            ensure_dir(target.parent)
            atomic_write_json(target, next_state.model_dump(mode="json", exclude_none=False))
            return next_state.model_copy(deep=True)

    def convert_legacy_state(
        self,
        project_id: str,
        node_id: str,
        payload: dict[str, Any] | None,
    ) -> NodeWorkflowStateV2:
        source = payload if isinstance(payload, dict) else {}
        phase = str(source.get("workflowPhase") or source.get("workflow_phase") or "idle").strip()
        latest_commit = _as_dict(source.get("latestCommit") or source.get("latest_commit"))
        execution_decision = _execution_decision_from_legacy(source.get("currentExecutionDecision"))
        audit_decision = _audit_decision_from_legacy(source.get("currentAuditDecision"))
        runtime_block = _as_dict(source.get("runtimeBlock") or source.get("runtime_block"))
        return NodeWorkflowStateV2(
            schema_version=WORKFLOW_SCHEMA_VERSION,
            state_version=0,
            project_id=project_id,
            node_id=str(source.get("nodeId") or source.get("node_id") or node_id),
            phase=LEGACY_PHASE_TO_V2.get(phase, "ready_for_execution"),  # type: ignore[arg-type]
            ask_thread_id=_optional_str(source.get("askThreadId") or source.get("ask_thread_id")),
            execution_thread_id=_optional_str(
                source.get("executionThreadId") or source.get("execution_thread_id")
            ),
            audit_thread_id=_optional_str(
                source.get("reviewThreadId")
                or source.get("review_thread_id")
                or source.get("auditLineageThreadId")
                or source.get("audit_lineage_thread_id")
            ),
            active_execution_run_id=_optional_str(
                source.get("activeExecutionRunId") or source.get("active_execution_run_id")
            ),
            latest_execution_run_id=_optional_str(
                source.get("latestExecutionRunId") or source.get("latest_execution_run_id")
            ),
            active_audit_run_id=_optional_str(
                source.get("activeReviewCycleId") or source.get("active_review_cycle_id")
            ),
            latest_audit_run_id=_optional_str(
                source.get("latestReviewCycleId") or source.get("latest_review_cycle_id")
            ),
            current_execution_decision=execution_decision,
            current_audit_decision=audit_decision,
            workspace_hash=(
                execution_decision.candidate_workspace_hash if execution_decision is not None else None
            ),
            base_commit_sha=_optional_str(latest_commit.get("initialSha") or latest_commit.get("initial_sha")),
            head_commit_sha=_optional_str(latest_commit.get("headSha") or latest_commit.get("head_sha")),
            accepted_sha=_optional_str(source.get("acceptedSha") or source.get("accepted_sha")),
            blocked_reason=_optional_str(runtime_block.get("message")),
            last_error=copy.deepcopy(runtime_block) if runtime_block else None,
            idempotency_records=copy.deepcopy(_as_dict(source.get("mutationCache"))),
            created_at=_optional_str(source.get("createdAt") or source.get("created_at")),
            updated_at=_optional_str(source.get("updatedAt") or source.get("updated_at")),
        )

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._storage.workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _normalize_canonical_state(
        self,
        payload: Any,
        *,
        project_id: str,
        node_id: str,
    ) -> NodeWorkflowStateV2:
        source = payload if isinstance(payload, dict) else {}
        if source.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
            source = {**source, "schema_version": WORKFLOW_SCHEMA_VERSION}
        return NodeWorkflowStateV2.model_validate(
            {
                **source,
                "project_id": project_id,
                "node_id": node_id,
            }
        )


def _execution_decision_from_legacy(payload: Any) -> ExecutionDecisionV2 | None:
    source = _as_dict(payload)
    if not source:
        return None
    return ExecutionDecisionV2(
        status=_optional_str(source.get("status")) or "current",
        sourceExecutionRunId=_optional_str(
            source.get("sourceExecutionRunId") or source.get("source_execution_run_id")
        ),
        executionTurnId=_optional_str(source.get("executionTurnId") or source.get("execution_turn_id")),
        candidateWorkspaceHash=_optional_str(
            source.get("candidateWorkspaceHash") or source.get("candidate_workspace_hash")
        ),
        summaryText=_optional_str(source.get("summaryText") or source.get("summary_text")),
        createdAt=_optional_str(source.get("createdAt") or source.get("created_at")),
    )


def _audit_decision_from_legacy(payload: Any) -> AuditDecisionV2 | None:
    source = _as_dict(payload)
    if not source:
        return None
    return AuditDecisionV2(
        status=_optional_str(source.get("status")) or "current",
        sourceAuditRunId=_optional_str(
            source.get("sourceReviewCycleId")
            or source.get("source_review_cycle_id")
            or source.get("sourceAuditRunId")
            or source.get("source_audit_run_id")
        ),
        reviewCommitSha=_optional_str(source.get("reviewCommitSha") or source.get("review_commit_sha")),
        finalReviewText=_optional_str(source.get("finalReviewText") or source.get("final_review_text")),
        reviewDisposition=_optional_str(source.get("reviewDisposition") or source.get("review_disposition")),
        createdAt=_optional_str(source.get("createdAt") or source.get("created_at")),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

