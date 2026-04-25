from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.tests.integration.test_workflow_v4_phase5 import (
    FakeSessionManager,
    _install_phase5_orchestrator,
    _project_with_confirmed_docs,
)


def test_v4_package_review_start_binds_thread_and_is_idempotent(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    _install_phase5_orchestrator(client, manager)
    repository = client.app.state.workflow_state_repository_v2
    state = repository.read_state(project_id, node_id).model_copy(
        deep=True,
        update={
            "phase": "done",
            "accepted_sha": "accepted-sha",
            "head_commit_sha": "accepted-sha",
        },
    )
    repository.write_state(project_id, node_id, state)

    payload = {
        "idempotencyKey": "package-review-start-1",
        "model": "gpt-5.4",
        "modelProvider": "openai",
    }
    first = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/package-review/start",
        json=payload,
    )
    second = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/package-review/start",
        json=payload,
    )

    assert first.status_code == 200, first.json()
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["accepted"] is True
    assert first_payload["threadId"] == "thread-1"
    assert first_payload["turnId"] == second_payload["turnId"]
    assert first_payload["workflowState"]["phase"] == "done"
    assert first_payload["workflowState"]["threads"]["packageReview"] == "thread-1"
    assert first_payload["workflowState"]["allowedActions"] == []
    assert len(manager.starts) == 1
    assert len(manager.injects) == 1
    assert len(manager.turns) == 1

    conflict = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/package-review/start",
        json={**payload, "model": "gpt-5.5"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ERR_WORKFLOW_IDEMPOTENCY_CONFLICT"

    duplicate_new_key = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/package-review/start",
        json={"idempotencyKey": "package-review-start-2"},
    )
    assert duplicate_new_key.status_code == 409
    assert duplicate_new_key.json()["code"] == "ERR_WORKFLOW_ACTION_NOT_ALLOWED"
    assert len(manager.turns) == 1


def test_v4_package_review_start_rejects_before_done(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    _install_phase5_orchestrator(client, manager)

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/package-review/start",
        json={"idempotencyKey": "package-review-too-early"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ERR_WORKFLOW_ACTION_NOT_ALLOWED"
    assert len(manager.turns) == 0
