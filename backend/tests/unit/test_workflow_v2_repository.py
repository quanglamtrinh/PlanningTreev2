from __future__ import annotations

import json

from backend.business.workflow_v2.models import default_workflow_state
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import complete_execution, start_execution
from backend.services.project_service import ProjectService


def _project_id(storage, workspace_root) -> str:
    return ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]


def test_read_state_returns_default_without_writing(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)

    state = repository.read_state(project_id, "node-1")

    assert state.project_id == project_id
    assert state.node_id == "node-1"
    assert state.phase == "ready_for_execution"
    assert not repository.canonical_path(project_id, "node-1").exists()
    assert not repository.legacy_path(project_id, "node-1").exists()


def test_write_state_uses_canonical_path_and_increments_version(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)
    state = start_execution(repository.read_state(project_id, "node-1"), execution_run_id="exec-run-1")

    first = repository.write_state(project_id, "node-1", state)
    second = repository.write_state(project_id, "node-1", first)

    assert first.state_version == 1
    assert second.state_version == 2
    assert second.created_at == first.created_at
    assert second.updated_at != first.updated_at
    assert repository.canonical_path(project_id, "node-1").exists()
    assert not repository.legacy_path(project_id, "node-1").exists()

    raw = json.loads(repository.canonical_path(project_id, "node-1").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["state_version"] == 2
    assert raw["phase"] == "executing"
    assert "allowed_actions" not in raw
    assert "workflowPhase" not in raw


def test_read_state_prefers_canonical_over_legacy(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)
    legacy_state = storage.workflow_state_store.default_state("node-1")
    legacy_state["workflowPhase"] = "failed"
    storage.workflow_state_store.write_state(project_id, "node-1", legacy_state)
    canonical = start_execution(
        default_workflow_state(project_id, "node-1"),
        execution_run_id="exec-run-1",
    )
    repository.write_state(project_id, "node-1", canonical)

    loaded = repository.read_state(project_id, "node-1")

    assert loaded.phase == "executing"
    assert loaded.state_version == 1


def test_legacy_read_through_converts_without_overwriting(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)
    legacy_state = storage.workflow_state_store.default_state("node-1")
    legacy_state.update(
        {
            "workflowPhase": "execution_decision_pending",
            "askThreadId": "thread-ask",
            "executionThreadId": "thread-exec",
            "reviewThreadId": "thread-review",
            "activeExecutionRunId": None,
            "latestExecutionRunId": "exec-run-1",
            "currentExecutionDecision": {
                "status": "current",
                "sourceExecutionRunId": "exec-run-1",
                "executionTurnId": "turn-1",
                "candidateWorkspaceHash": "sha256:workspace",
                "summaryText": "implemented",
                "createdAt": "2026-04-24T00:00:00Z",
            },
            "latestCommit": {
                "sourceAction": "review_in_audit",
                "initialSha": "base-sha",
                "headSha": "head-sha",
                "commitMessage": "commit",
                "committed": True,
                "recordedAt": "2026-04-24T00:00:00Z",
            },
            "mutationCache": {"finish_task:key": {"accepted": True}},
        }
    )
    storage.workflow_state_store.write_state(project_id, "node-1", legacy_state)

    loaded = repository.read_state(project_id, "node-1")

    assert loaded.phase == "execution_completed"
    assert loaded.ask_thread_id == "thread-ask"
    assert loaded.execution_thread_id == "thread-exec"
    assert loaded.audit_thread_id == "thread-review"
    assert loaded.latest_execution_run_id == "exec-run-1"
    assert loaded.current_execution_decision is not None
    assert loaded.current_execution_decision.candidate_workspace_hash == "sha256:workspace"
    assert loaded.base_commit_sha == "base-sha"
    assert loaded.head_commit_sha == "head-sha"
    assert loaded.idempotency_records == {"finish_task:key": {"accepted": True}}
    assert repository.legacy_path(project_id, "node-1").exists()
    assert not repository.canonical_path(project_id, "node-1").exists()


def test_legacy_audit_phase_mapping(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)
    legacy_state = storage.workflow_state_store.default_state("node-1")
    legacy_state.update(
        {
            "workflowPhase": "audit_decision_pending",
            "activeReviewCycleId": None,
            "latestReviewCycleId": "audit-run-1",
            "currentAuditDecision": {
                "sourceReviewCycleId": "audit-run-1",
                "reviewCommitSha": "review-sha",
                "finalReviewText": "ok",
                "reviewDisposition": "accepted",
            },
        }
    )
    storage.workflow_state_store.write_state(project_id, "node-1", legacy_state)

    loaded = repository.read_state(project_id, "node-1")

    assert loaded.phase == "review_pending"
    assert loaded.latest_audit_run_id == "audit-run-1"
    assert loaded.current_audit_decision is not None
    assert loaded.current_audit_decision.review_commit_sha == "review-sha"
