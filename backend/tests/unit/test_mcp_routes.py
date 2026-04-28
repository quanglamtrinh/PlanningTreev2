from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


class FakeMcpManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def mcp_runtime_refresh(self, *, thread_id: str, payload: dict) -> dict:
        self.calls.append({"method": "refresh", "threadId": thread_id, "payload": dict(payload)})
        return {"refreshed": True}

    def mcp_server_status_list(self, *, thread_id: str, payload: dict) -> dict:
        self.calls.append({"method": "status", "threadId": thread_id, "payload": dict(payload)})
        return {"servers": []}

    def mcp_resource_read(self, *, thread_id: str, payload: dict) -> dict:
        self.calls.append({"method": "resource", "threadId": thread_id, "payload": dict(payload)})
        return {"contents": []}

    def mcp_server_tool_call(self, *, thread_id: str, payload: dict) -> dict:
        self.calls.append({"method": "tool", "threadId": thread_id, "payload": dict(payload)})
        return {"content": [{"type": "text", "text": payload.get("arguments", {}).get("message", "")}], "isError": False}

    def mcp_server_oauth_login(self, payload: dict) -> dict:
        self.calls.append({"method": "oauth", "payload": dict(payload)})
        return {"login": "started"}


class FakeSessionManager:
    def __init__(self) -> None:
        self.thread_starts: list[dict[str, Any]] = []
        self.existing_threads: set[str] = set()

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(payload or {})
        self.thread_starts.append(params)
        thread_id = f"root-thread-{len(self.thread_starts)}"
        self.existing_threads.add(thread_id)
        return {"thread": {"id": thread_id}}

    def native_rollout_metadata_exists(self, thread_id: str) -> bool:
        return thread_id in self.existing_threads


def _attach_project(client: TestClient, workspace_root) -> tuple[str, str]:
    response = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    snapshot = response.json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def test_root_thread_ensure_starts_and_reuses_root_session(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, root_id = _attach_project(client, workspace_root)
    manager = FakeSessionManager()
    client.app.state.session_manager_v2 = manager

    first = client.post(
        f"/v4/projects/{project_id}/nodes/{root_id}/root-thread/ensure",
        json={"model": "gpt-5.4", "modelProvider": "openai"},
    )
    second = client.post(f"/v4/projects/{project_id}/nodes/{root_id}/root-thread/ensure", json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == {"threadId": "root-thread-1", "role": "root"}
    assert second.json()["data"] == {"threadId": "root-thread-1", "role": "root"}
    assert manager.thread_starts == [
        {"cwd": str(workspace_root.resolve()), "model": "gpt-5.4", "modelProvider": "openai"}
    ]
    session = client.app.state.storage.chat_state_store.read_session(
        project_id, root_id, thread_role="root"
    )
    assert session["thread_id"] == "root-thread-1"


def test_root_thread_ensure_rejects_non_root_node(client: TestClient, workspace_root) -> None:
    project_id, root_id = _attach_project(client, workspace_root)
    client.app.state.session_manager_v2 = FakeSessionManager()
    created = client.post(f"/v3/projects/{project_id}/nodes", json={"parent_id": root_id})
    assert created.status_code == 200
    child_id = created.json()["tree_state"]["active_node_id"]

    response = client.post(f"/v4/projects/{project_id}/nodes/{child_id}/root-thread/ensure", json={})

    assert response.status_code >= 400


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
            "method": "tool",
            "threadId": "thread-1",
            "payload": {
                "server": "echo",
                "tool": "echo",
                "arguments": {"message": "hello mcp"},
                "_meta": {"requestId": "req-1"},
            },
        }
    ]



def test_mcp_runtime_routes_proxy_payloads(client: TestClient) -> None:
    manager = FakeMcpManager()
    client.app.state.session_manager_v2 = manager

    assert client.post(
        "/v4/session/threads/thread-1/mcp/refresh",
        json={"mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
    ).json()["data"] == {"refreshed": True}
    assert client.get("/v4/session/threads/thread-1/mcp/status?cursor=abc&limit=10&detail=full").json()["data"] == {"servers": []}
    assert client.post(
        "/v4/session/threads/thread-1/mcp/resource/read",
        json={"server": "fs", "uri": "file:///tmp/a.txt"},
    ).json()["data"] == {"contents": []}
    assert client.post(
        "/v4/session/mcp/oauth/login",
        json={"name": "remote", "scopes": ["read"], "timeoutSecs": 5},
    ).json()["data"] == {"login": "started"}

    assert manager.calls == [
        {
            "method": "refresh",
            "threadId": "thread-1",
            "payload": {"mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        },
        {"method": "status", "threadId": "thread-1", "payload": {"cursor": "abc", "limit": 10, "detail": "full"}},
        {"method": "resource", "threadId": "thread-1", "payload": {"server": "fs", "uri": "file:///tmp/a.txt"}},
        {"method": "oauth", "payload": {"name": "remote", "scopes": ["read"], "timeoutSecs": 5}},
    ]
