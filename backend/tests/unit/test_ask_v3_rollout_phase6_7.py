from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.services.ask_rollout_metrics_service import AskRolloutMetricsService


def _attach_project(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    response = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    payload = response.json()
    return payload["project"]["id"], payload["tree_state"]["root_node_id"]


def test_ask_rollout_metrics_service_computes_rates() -> None:
    service = AskRolloutMetricsService()
    service.record_stream_session()
    service.record_stream_error()
    service.record_shaping_action_started()
    service.record_shaping_action_started()
    service.record_shaping_action_failed()

    payload = service.as_public_payload()
    assert payload["ask_stream_session_total"] == 1
    assert payload["ask_stream_error_total"] == 1
    assert payload["ask_stream_error_rate"] == 1.0
    assert payload["ask_shaping_action_total"] == 2
    assert payload["ask_shaping_action_failed_total"] == 1
    assert payload["ask_shaping_action_failed_rate"] == 0.5


def test_bootstrap_ask_rollout_metrics_event_endpoints(client: TestClient) -> None:
    initial = client.get("/v1/ask-rollout/metrics")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["ask_stream_reconnect_total"] == 0
    assert initial_payload["ask_stream_error_total"] == 0

    reconnect = client.post("/v1/ask-rollout/metrics/events", json={"event": "stream_reconnect"})
    assert reconnect.status_code == 200
    assert reconnect.json() == {"ok": True}

    stream_error = client.post("/v1/ask-rollout/metrics/events", json={"event": "stream_error"})
    assert stream_error.status_code == 200
    assert stream_error.json() == {"ok": True}

    updated = client.get("/v1/ask-rollout/metrics")
    assert updated.status_code == 200
    updated_payload = updated.json()
    assert updated_payload["ask_stream_reconnect_total"] == 1
    assert updated_payload["ask_stream_error_total"] == 1


def test_v1_legacy_chat_ask_handlers_are_disabled(client: TestClient) -> None:
    session = client.get("/v1/projects/project-x/nodes/node-y/chat/session")
    assert session.status_code == 400
    assert session.json()["code"] == "invalid_request"
    assert "no longer served on /v1 chat APIs" in session.json()["message"]

    message = client.post(
        "/v1/projects/project-x/nodes/node-y/chat/message",
        json={"content": "hello"},
    )
    assert message.status_code == 400
    assert message.json()["code"] == "invalid_request"

    reset = client.post("/v1/projects/project-x/nodes/node-y/chat/reset")
    assert reset.status_code == 400
    assert reset.json()["code"] == "invalid_request"

    events = client.get("/v1/projects/project-x/nodes/node-y/chat/events")
    assert events.status_code == 400
    assert events.json()["code"] == "invalid_request"


def test_v2_ask_thread_role_is_rejected(client: TestClient) -> None:
    snapshot = client.get("/v2/projects/project-x/nodes/node-y/threads/ask_planning")
    assert snapshot.status_code == 400
    snapshot_payload = snapshot.json()
    assert snapshot_payload["ok"] is False
    assert snapshot_payload["error"]["code"] == "invalid_request"
    assert "Use /v3 by-id APIs." in snapshot_payload["error"]["message"]

    turn = client.post(
        "/v2/projects/project-x/nodes/node-y/threads/ask_planning/turns",
        json={"text": "hello"},
    )
    assert turn.status_code == 400
    turn_payload = turn.json()
    assert turn_payload["ok"] is False
    assert turn_payload["error"]["code"] == "invalid_request"


def test_v3_ask_by_id_returns_typed_error_when_backend_gate_off(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _attach_project(client, workspace_root)
    thread_id = "ask-thread-disabled-1"
    storage = client.app.state.storage

    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "ask_planning",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "ask_planning",
            "threadId": thread_id,
            "forkReason": "ask_bootstrap",
            "lineageRootThreadId": thread_id,
        },
    )

    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "ask_planning")
    snapshot["threadId"] = thread_id
    snapshot["snapshotVersion"] = 1
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "ask_planning", snapshot)

    client.app.state.ask_v3_backend_enabled = False
    try:
        response = client.get(
            f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
            params={"node_id": node_id},
        )
    finally:
        client.app.state.ask_v3_backend_enabled = True

    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ask_v3_disabled"
