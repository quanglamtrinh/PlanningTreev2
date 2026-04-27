from __future__ import annotations

from fastapi.testclient import TestClient


class FakeMcpManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def mcp_server_tool_call(self, *, thread_id: str, payload: dict) -> dict:
        self.calls.append({"threadId": thread_id, "payload": dict(payload)})
        return {"content": [{"type": "text", "text": payload.get("arguments", {}).get("message", "")}], "isError": False}


def test_mcp_tool_call_route_proxies_echo_payload(client: TestClient) -> None:
    manager = FakeMcpManager()
    client.app.state.session_manager_v2 = manager

    response = client.post(
        "/v4/session/threads/thread-1/mcp/tool/call",
        json={
            "server": "echo",
            "tool": "echo",
            "arguments": {"message": "hello mcp"},
            "_meta": {"requestId": "req-1"},
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "content": [{"type": "text", "text": "hello mcp"}],
        "isError": False,
    }
    assert manager.calls == [
        {
            "threadId": "thread-1",
            "payload": {
                "server": "echo",
                "tool": "echo",
                "arguments": {"message": "hello mcp"},
                "_meta": {"requestId": "req-1"},
            },
        }
    ]
