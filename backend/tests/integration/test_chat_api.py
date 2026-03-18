from __future__ import annotations

from fastapi.testclient import TestClient


def test_execution_chat_route_family_is_not_registered(client: TestClient) -> None:
    paths = {route.path for route in client.app.router.routes}

    assert "/v1/projects/{project_id}/nodes/{node_id}/chat/session" not in paths
    assert "/v1/projects/{project_id}/nodes/{node_id}/chat/messages" not in paths
    assert "/v1/projects/{project_id}/nodes/{node_id}/chat/reset" not in paths
    assert "/v1/projects/{project_id}/nodes/{node_id}/chat/events" not in paths


def test_execution_chat_routes_return_not_found(client: TestClient) -> None:
    project_id = "12345678-1234-1234-1234-123456789abc"
    node_id = "node-legacy"

    session_response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/chat/session")
    message_response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "hello"},
    )
    reset_response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/chat/reset")
    events_response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/chat/events")

    assert session_response.status_code == 404
    assert message_response.status_code in {404, 405}
    assert reset_response.status_code in {404, 405}
    assert events_response.status_code == 404
