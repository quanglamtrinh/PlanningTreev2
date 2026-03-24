from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.services import chat_service as chat_service_module


class SlowCheckpointCodexClient:
    def __init__(self, *, response_text: str = "Hello from AI") -> None:
        self.response_text = response_text
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"chat-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        raise CodexTransportError("thread not found", "not_found")

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        thread_id = str(kwargs.get("thread_id", ""))
        on_delta = kwargs.get("on_delta")
        if on_delta:
            on_delta("Hello ")
            time.sleep(0.03)
            on_delta("from AI")
            time.sleep(0.1)
        return {"stdout": self.response_text, "thread_id": thread_id}


class ExecutionCodexClient:
    def __init__(self, *, response_text: str = "Execution complete") -> None:
        self.response_text = response_text
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"exec-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        thread_id = str(kwargs.get("thread_id", ""))
        cwd = kwargs.get("cwd")
        if isinstance(cwd, str) and cwd:
            from pathlib import Path

            Path(cwd, "integration-finish-task.txt").write_text("done\n", encoding="utf-8")
        return {"stdout": self.response_text, "thread_id": thread_id}


def _setup_project(client: TestClient, workspace_root) -> tuple[str, str]:
    resp = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert resp.status_code == 200
    snap = resp.json()
    project_id = snap["project"]["id"]
    root_id = snap["tree_state"]["root_node_id"]
    return project_id, root_id


def test_get_session_empty(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/chat/session")
    assert resp.status_code == 200
    session = resp.json()
    assert session["thread_id"] is None
    assert session["messages"] == []


def test_get_session_nonexistent_node(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    resp = client.get(f"/v1/projects/{project_id}/nodes/nonexistent/chat/session")
    assert resp.status_code == 404


def test_send_message_empty_content(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/chat/message",
        json={"content": "   "},
    )
    assert resp.status_code == 400


def test_reset_session(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/chat/reset")
    assert resp.status_code == 200
    session = resp.json()
    assert session["messages"] == []


def test_chat_session_honors_thread_role_query(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.get(
        f"/v1/projects/{project_id}/nodes/{root_id}/chat/session",
        params={"thread_role": "audit"},
    )
    assert resp.status_code == 200
    assert resp.json()["thread_role"] == "audit"


def test_reset_nonexistent_node(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    resp = client.post(f"/v1/projects/{project_id}/nodes/nonexistent/chat/reset")
    assert resp.status_code == 404


def test_chat_events_nonexistent_node_returns_404(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    response = client.get(f"/v1/projects/{project_id}/nodes/nonexistent/chat/events")
    assert response.status_code == 404


def test_get_session_returns_partial_content_mid_stream(client: TestClient, workspace_root, monkeypatch):
    monkeypatch.setattr(chat_service_module, "_DRAFT_FLUSH_INTERVAL_SEC", 0.01)
    client.app.state.chat_service._codex_client = SlowCheckpointCodexClient()

    project_id, root_id = _setup_project(client, workspace_root)
    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/chat/message",
        json={"content": "Hello"},
    )
    assert response.status_code == 200

    deadline = time.time() + 2.0
    streaming_session = None
    while time.time() < deadline:
        session_response = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/chat/session")
        assert session_response.status_code == 200
        candidate = session_response.json()
        if candidate["messages"] and candidate["messages"][1]["status"] == "streaming":
            streaming_session = candidate
            break
        time.sleep(0.02)

    assert streaming_session is not None
    assert streaming_session["messages"][1]["content"].startswith("Hello")

    completed_session = None
    while time.time() < deadline:
        session_response = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/chat/session")
        candidate = session_response.json()
        if candidate["messages"] and candidate["messages"][1]["status"] == "completed":
            completed_session = candidate
            break
        time.sleep(0.02)

    assert completed_session is not None
    assert completed_session["messages"][1]["content"] == "Hello from AI"


def test_finish_task_route_returns_detail_state_and_creates_execution_session(
    client: TestClient,
    workspace_root,
):
    client.app.state.finish_task_service._codex_client = ExecutionCodexClient()
    project_id, root_id = _setup_project(client, workspace_root)

    frame_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    assert frame_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-frame").status_code == 200

    spec_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    assert spec_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-spec").status_code == 200

    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    detail_before = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/detail-state").json()
    assert detail_before["can_finish_task"] is True

    finish_resp = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/finish-task")
    assert finish_resp.status_code == 200
    payload = finish_resp.json()
    assert payload["execution_started"] is True
    assert payload["shaping_frozen"] is True

    deadline = time.time() + 2.0
    execution_session = None
    while time.time() < deadline:
        session_resp = client.get(
            f"/v1/projects/{project_id}/nodes/{root_id}/chat/session",
            params={"thread_role": "execution"},
        )
        assert session_resp.status_code == 200
        session = session_resp.json()
        if session["messages"]:
            execution_session = session
            if session["messages"][0]["status"] in {"completed", "error"}:
                break
        time.sleep(0.02)

    assert execution_session is not None
    assert execution_session["thread_role"] == "execution"
    assert execution_session["messages"][0]["role"] == "assistant"
