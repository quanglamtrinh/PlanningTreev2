from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.tests.integration.test_workflow_v4_phase4 import (
    FakeSessionManager,
    _install_binding_service_with_publisher,
    _project_with_confirmed_docs,
    _write_confirmed_docs,
)


class RecordingBroker:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def publish(self, event: dict[str, object]) -> None:
        self.events.append(dict(event))


def test_v4_workflow_state_detects_stale_context_and_rebase_clears_it(
    client: TestClient,
    workspace_root: Path,
) -> None:
    manager = FakeSessionManager()
    _install_binding_service_with_publisher(client, manager)
    project_id, node_id, node_dir = _project_with_confirmed_docs(client, workspace_root)

    ensure = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={"idempotencyKey": "ensure-thread:phase8"},
    )
    assert ensure.status_code == 200, ensure.json()
    first_hash = ensure.json()["binding"]["contextPacketHash"]

    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")

    state_response = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state")

    assert state_response.status_code == 200, state_response.json()
    stale_payload = state_response.json()
    assert stale_payload["context"]["stale"] is True
    assert stale_payload["allowedActions"] == ["rebase_context"]
    stale_binding = stale_payload["context"]["staleBindings"][0]
    assert stale_binding["role"] == "execution"
    assert stale_binding["threadId"] == "thread-1"
    assert stale_binding["currentContextPacketHash"] == first_hash
    assert stale_binding["nextContextPacketHash"] != first_hash

    rebase = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/context/rebase",
        json={
            "idempotencyKey": "context-rebase:phase8",
            "expectedWorkflowVersion": stale_payload["version"],
        },
    )

    assert rebase.status_code == 200, rebase.json()
    payload = rebase.json()
    assert payload["rebased"] is True
    assert payload["updatedBindings"] == [
        {
            "role": "execution",
            "threadId": "thread-1",
            "contextPacketHash": stale_binding["nextContextPacketHash"],
        }
    ]
    assert payload["workflowState"]["context"]["stale"] is False
    assert payload["workflowState"]["context"]["staleBindings"] == []
    assert len(manager.injects) == 2
    update_item = manager.injects[1]["payload"]["items"][0]
    assert update_item["metadata"]["packetKind"] == "context_update"
    assert update_item["metadata"]["contextPacketHash"] == stale_binding["nextContextPacketHash"]
    assert '"kind":"context_update"' in update_item["text"]


def test_v4_normal_workflow_actions_are_blocked_while_context_is_stale(
    client: TestClient,
    workspace_root: Path,
) -> None:
    manager = FakeSessionManager()
    _install_binding_service_with_publisher(client, manager)
    project_id, node_id, node_dir = _project_with_confirmed_docs(client, workspace_root)
    assert client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={"idempotencyKey": "ensure-thread:phase8-block"},
    ).status_code == 200
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "start-execution:phase8-block"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ERR_WORKFLOW_CONTEXT_STALE"
    state_payload = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state").json()
    assert state_payload["allowedActions"] == ["rebase_context"]


def test_v4_context_rebase_publishes_native_workflow_events(
    client: TestClient,
    workspace_root: Path,
) -> None:
    manager = FakeSessionManager()
    broker = RecordingBroker()
    client.app.state.workflow_event_broker = broker
    _install_binding_service_with_publisher(client, manager)
    project_id, node_id, node_dir = _project_with_confirmed_docs(client, workspace_root)
    assert client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={"idempotencyKey": "ensure-thread:phase8-events"},
    ).status_code == 200
    broker.events.clear()
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")
    stale_payload = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state").json()

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/context/rebase",
        json={
            "idempotencyKey": "context-rebase:phase8-events",
            "expectedWorkflowVersion": stale_payload["version"],
        },
    )

    assert response.status_code == 200, response.json()
    assert [event["type"] for event in broker.events] == [
        "workflow/context_stale",
        "workflow/action_completed",
        "workflow/state_changed",
    ]
    completed = broker.events[1]
    assert completed["action"] == "rebase_context"
    assert completed["details"]["updatedBindings"][0]["role"] == "execution"


def test_v4_context_rebase_rejects_stale_expected_workflow_version(
    client: TestClient,
    workspace_root: Path,
) -> None:
    manager = FakeSessionManager()
    _install_binding_service_with_publisher(client, manager)
    project_id, node_id, node_dir = _project_with_confirmed_docs(client, workspace_root)
    assert client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={"idempotencyKey": "ensure-thread:phase8-version"},
    ).status_code == 200
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")
    stale_payload = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state").json()

    rebase = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/context/rebase",
        json={
            "idempotencyKey": "context-rebase:phase8-version",
            "expectedWorkflowVersion": stale_payload["version"] - 1,
        },
    )

    assert rebase.status_code == 409
    assert rebase.json()["code"] == "ERR_WORKFLOW_VERSION_CONFLICT"
