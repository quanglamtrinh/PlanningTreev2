from __future__ import annotations

from backend.business.workflow_v2.models import (
    ExecutionDecisionV2,
    NodeWorkflowStateV2,
    ThreadBinding,
    default_workflow_state,
    workflow_state_to_response,
)
from backend.business.workflow_v2.state_machine import derive_allowed_actions


def test_default_state_uses_canonical_internal_shape() -> None:
    state = default_workflow_state("project-1", "node-1")

    assert state.schema_version == 1
    assert state.state_version == 0
    assert state.phase == "ready_for_execution"
    dumped = state.model_dump(mode="json")
    assert "allowed_actions" not in dumped
    assert "workflowPhase" not in dumped


def test_public_response_uses_v4_camel_case_shape() -> None:
    state = NodeWorkflowStateV2(
        project_id="project-1",
        node_id="node-1",
        phase="execution_completed",
        state_version=7,
        execution_thread_id="thread-exec",
        current_execution_decision=ExecutionDecisionV2(
            sourceExecutionRunId="run-1",
            executionTurnId="turn-1",
            candidateWorkspaceHash="sha256:workspace",
            summaryText="done",
            createdAt="2026-04-24T00:00:00Z",
        ),
        frame_version=2,
        spec_version=3,
        split_manifest_version=4,
    )

    payload = workflow_state_to_response(
        state,
        allowed_actions=derive_allowed_actions(state),
    ).to_public_dict()

    assert payload["schemaVersion"] == 1
    assert payload["projectId"] == "project-1"
    assert payload["nodeId"] == "node-1"
    assert payload["phase"] == "execution_completed"
    assert payload["version"] == 7
    assert payload["threads"] == {
        "askPlanning": None,
        "execution": "thread-exec",
        "audit": None,
        "packageReview": None,
    }
    assert payload["decisions"]["execution"]["candidateWorkspaceHash"] == "sha256:workspace"
    assert payload["context"] == {
        "frameVersion": 2,
        "specVersion": 3,
        "splitManifestVersion": 4,
        "stale": False,
        "staleReason": None,
    }
    assert payload["allowedActions"] == ["review_in_audit", "mark_done_from_execution"]
    assert "workflowPhase" not in payload


def test_thread_binding_serializes_camel_case_public_fields() -> None:
    binding = ThreadBinding(
        projectId="project-1",
        nodeId="node-1",
        role="execution",
        threadId="thread-1",
        createdFrom="new_thread",
        contextPacketHash="sha256:packet",
    )

    assert binding.model_dump(by_alias=True, mode="json") == {
        "projectId": "project-1",
        "nodeId": "node-1",
        "role": "execution",
        "threadId": "thread-1",
        "createdFrom": "new_thread",
        "sourceVersions": {
            "frameVersion": None,
            "specVersion": None,
            "splitManifestVersion": None,
        },
        "contextPacketHash": "sha256:packet",
        "createdAt": None,
        "updatedAt": None,
    }

