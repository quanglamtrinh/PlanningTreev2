from __future__ import annotations

from pathlib import Path

import pytest

from backend.business.workflow_v2.errors import (
    WorkflowActionNotAllowedError,
    WorkflowArtifactVersionConflictError,
)
from backend.business.workflow_v2.models import default_workflow_state
from backend.business.workflow_v2.state_machine import (
    complete_audit,
    complete_execution,
    derive_allowed_actions,
    improve_execution,
    mark_done_from_audit,
    mark_done_from_execution,
    start_audit,
    start_execution,
    start_package_review,
)


def test_execution_and_audit_happy_path_transitions() -> None:
    state = default_workflow_state("project-1", "node-1")
    assert derive_allowed_actions(state) == ["start_execution"]

    executing = start_execution(state, execution_run_id="exec-run-1", execution_thread_id="thread-exec")
    assert executing.phase == "executing"
    assert derive_allowed_actions(executing) == []

    execution_done = complete_execution(
        executing,
        candidate_workspace_hash="sha256:workspace",
        execution_turn_id="turn-1",
        head_commit_sha="exec-sha",
        summary_text="implemented",
    )
    assert execution_done.phase == "execution_completed"
    assert execution_done.current_execution_decision is not None
    assert derive_allowed_actions(execution_done) == ["review_in_audit", "mark_done_from_execution"]

    auditing = start_audit(
        execution_done,
        audit_run_id="audit-run-1",
        audit_thread_id="thread-audit",
        expected_workspace_hash="sha256:workspace",
    )
    assert auditing.phase == "audit_running"
    assert auditing.audit_thread_id == "thread-audit"

    review_pending = complete_audit(
        auditing,
        review_commit_sha="review-sha",
        final_review_text="needs polish",
        review_disposition="changes_requested",
    )
    assert review_pending.phase == "review_pending"
    assert derive_allowed_actions(review_pending) == ["improve_in_execution", "mark_done_from_audit"]

    improving = improve_execution(
        review_pending,
        expected_review_commit_sha="review-sha",
        execution_run_id="exec-run-2",
    )
    assert improving.phase == "executing"
    assert improving.current_audit_decision is None


def test_mark_done_from_execution_validates_workspace_hash() -> None:
    state = complete_execution(
        start_execution(default_workflow_state("project-1", "node-1"), execution_run_id="exec-run-1"),
        candidate_workspace_hash="sha256:workspace",
        head_commit_sha="exec-sha",
    )

    with pytest.raises(WorkflowArtifactVersionConflictError) as exc:
        mark_done_from_execution(state, expected_workspace_hash="sha256:other")

    assert exc.value.code == "ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT"
    done = mark_done_from_execution(state, expected_workspace_hash="sha256:workspace")
    assert done.phase == "done"


def test_mark_done_from_audit_validates_review_commit() -> None:
    state = complete_audit(
        start_audit(
            complete_execution(
                start_execution(default_workflow_state("project-1", "node-1"), execution_run_id="exec-run-1"),
                candidate_workspace_hash="sha256:workspace",
            ),
            audit_run_id="audit-run-1",
            expected_workspace_hash="sha256:workspace",
        ),
        review_commit_sha="review-sha",
    )

    with pytest.raises(WorkflowArtifactVersionConflictError) as exc:
        mark_done_from_audit(state, expected_review_commit_sha="other-sha")

    assert exc.value.code == "ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT"
    done = mark_done_from_audit(state, expected_review_commit_sha="review-sha")
    assert done.phase == "done"
    assert done.accepted_sha == "review-sha"
    assert derive_allowed_actions(done) == ["start_package_review"]

    package_reviewing = start_package_review(done, package_review_thread_id="thread-package")
    assert package_reviewing.phase == "done"
    assert package_reviewing.package_review_thread_id == "thread-package"
    assert derive_allowed_actions(package_reviewing) == []


def test_invalid_transition_raises_stable_action_error() -> None:
    state = start_execution(default_workflow_state("project-1", "node-1"), execution_run_id="exec-run-1")

    with pytest.raises(WorkflowActionNotAllowedError) as exc:
        start_execution(state, execution_run_id="exec-run-2")

    assert exc.value.code == "ERR_WORKFLOW_ACTION_NOT_ALLOWED"
    assert exc.value.details["phase"] == "executing"


def test_state_machine_has_no_forbidden_runtime_imports() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "backend/business/workflow_v2/state_machine.py").read_text(encoding="utf-8")
    forbidden = [
        "backend.storage",
        "backend.routes",
        "session_core",
        "sse",
        "codex",
        "ExecutionAuditWorkflowService",
        "execution_audit_workflow_service",
    ]

    assert [token for token in forbidden if token in source] == []
