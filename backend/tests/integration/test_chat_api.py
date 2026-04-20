from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.services import planningtree_workspace
from backend.services import chat_service as chat_service_module
from backend.tests.conftest import init_git_repo


class SlowCheckpointCodexClient:
    def __init__(self, *, response_text: str = "Hello from AI") -> None:
        self.response_text = response_text
        self.started_threads: list[str] = []
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"chat-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"chat-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

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
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"exec-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"exec-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        thread_id = str(kwargs.get("thread_id", ""))
        cwd = kwargs.get("cwd")
        if isinstance(cwd, str) and cwd:
            Path(cwd, "integration-finish-task.txt").write_text("done\n", encoding="utf-8")
        return {"stdout": self.response_text, "thread_id": thread_id}


class IntegrationRollupCodexClient:
    def __init__(self, *, summary: str = "Integration complete") -> None:
        self.summary = summary
        self.started_threads: list[str] = []
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"integration-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"exec-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"integration-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        payload = json.dumps({"summary": self.summary})
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            on_delta(payload)
        return {"stdout": payload, "thread_id": str(kwargs.get("thread_id") or "")}


def _setup_project(client: TestClient, workspace_root) -> tuple[str, str]:
    resp = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert resp.status_code == 200
    snap = resp.json()
    project_id = snap["project"]["id"]
    root_id = snap["tree_state"]["root_node_id"]
    return project_id, root_id


def _set_chat_codex_client(client: TestClient, codex_client: object) -> None:
    client.app.state.chat_service._codex_client = codex_client
    client.app.state.thread_lineage_service._codex_client = codex_client


def _set_execution_codex_client(client: TestClient, codex_client: object) -> None:
    client.app.state.finish_task_service._codex_client = codex_client
    client.app.state.thread_lineage_service._codex_client = codex_client


def _add_review_node(client: TestClient, project_id: str, parent_id: str) -> str:
    review_id = "review-001"
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": 1,
        "display_order": 99,
        "hierarchical_number": "1.R",
        "created_at": "2026-01-01T00:00:00Z",
    }
    snapshot["tree_state"]["node_index"][parent_id]["review_node_id"] = review_id
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    return review_id


def _add_child(
    client: TestClient,
    project_id: str,
    parent_id: str,
    *,
    node_id: str,
    title: str,
    description: str,
    status: str = "ready",
) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    child_ids = [*parent.get("child_ids", []), node_id]
    parent["child_ids"] = child_ids
    node_index[node_id] = {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": status,
        "node_kind": "original",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(child_ids) - 1,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.{len(child_ids)}",
        "created_at": "2026-01-01T00:00:00Z",
    }
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def _write_confirmed_frame(client: TestClient, project_id: str, node_id: str, content: str) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "confirmed_revision": 1,
                "confirmed_at": "2026-01-01T00:00:00Z",
                "confirmed_content": content,
            }
        ),
        encoding="utf-8",
    )


def _wait_for_integration_completion(
    client: TestClient, project_id: str, review_node_id: str, *, timeout_sec: float = 2.0
) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id,
            review_node_id,
            thread_role="audit",
        )
        if not session.get("active_turn_id"):
            messages = session.get("messages", [])
            assistant = next(
                (
                    message
                    for message in reversed(messages)
                    if isinstance(message, dict) and message.get("role") == "assistant"
                ),
                None,
            )
            if assistant is not None and assistant.get("status") == "completed":
                return session
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for integration completion.")


def test_get_session_empty(client: TestClient, workspace_root):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/chat/session")
    assert resp.status_code == 200
    session = resp.json()
    assert session["thread_id"] is not None
    assert session["fork_reason"] == "ask_bootstrap"
    assert session["forked_from_role"] == "audit"
    assert session["messages"] == []


def test_get_session_nonexistent_node(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    resp = client.get(f"/v3/projects/{project_id}/nodes/nonexistent/chat/session")
    assert resp.status_code == 404


def test_send_message_empty_content(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/message",
        json={"content": "   "},
    )
    assert resp.status_code == 400


def test_reset_session(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/chat/reset")
    assert resp.status_code == 200
    session = resp.json()
    assert session["messages"] == []


def test_chat_session_honors_thread_role_query(client: TestClient, workspace_root):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.get(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/session",
        params={"thread_role": "audit"},
    )
    assert resp.status_code == 200
    assert resp.json()["thread_role"] == "audit"


def test_audit_session_bootstraps_lineage_without_seed_replay(client: TestClient, workspace_root):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["title"] = "Parent Task"
    snapshot["tree_state"]["node_index"][root_id]["description"] = "Parent summary"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    _add_child(
        client,
        project_id,
        root_id,
        node_id="child-seed",
        title="Auth guard",
        description="Add route guard\n\nWhy now: Gate requests",
    )
    review_id = _add_review_node(client, project_id, root_id)
    client.app.state.storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:base",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:k1",
                    "summary": "Guard accepted",
                    "source_node_id": "child-seed",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    response = client.get(
        f"/v3/projects/{project_id}/nodes/child-seed/chat/session",
        params={"thread_role": "audit"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_role"] == "audit"
    assert payload["thread_id"] is not None
    assert payload["fork_reason"] == "child_activation"
    assert payload["messages"] == []


def test_task_node_rejects_invalid_thread_role_pair(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    resp = client.get(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/session",
        params={"thread_role": "integration"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_request"


def test_review_node_accepts_audit_thread_role(client: TestClient, workspace_root):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)
    resp = client.get(
        f"/v3/projects/{project_id}/nodes/{review_id}/chat/session",
        params={"thread_role": "audit"},
    )
    assert resp.status_code == 200
    assert resp.json()["thread_role"] == "audit"


def test_review_node_rejects_integration_thread_role(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)
    resp = client.get(
        f"/v3/projects/{project_id}/nodes/{review_id}/chat/session",
        params={"thread_role": "integration"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_request"


def test_review_audit_session_stays_empty_when_rollup_ready(
    client: TestClient,
    workspace_root,
):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["title"] = "Build auth package"
    snapshot["tree_state"]["node_index"][root_id]["description"] = "Parent package"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    _add_child(
        client,
        project_id,
        root_id,
        node_id="child-a",
        title="Auth guard",
        description="Guard routes\n\nWhy now: First gate",
        status="done",
    )
    _add_child(
        client,
        project_id,
        root_id,
        node_id="child-b",
        title="Session parser",
        description="Parse cookies\n\nWhy now: After gate",
        status="done",
    )
    review_id = _add_review_node(client, project_id, root_id)
    client.app.state.storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:k0",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:k1",
                    "summary": "Guard accepted",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
                {
                    "label": "K2",
                    "sha": "sha256:k2",
                    "summary": "Parser accepted",
                    "source_node_id": "child-b",
                    "accepted_at": "2026-01-01T02:00:00Z",
                },
            ],
            "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )
    _write_confirmed_frame(client, project_id, root_id, "# Parent Frame\nShip auth package\n")

    response = client.get(
        f"/v3/projects/{project_id}/nodes/{review_id}/chat/session",
        params={"thread_role": "audit"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_role"] == "audit"
    assert payload["messages"] == []


def test_review_audit_session_includes_assistant_output_after_auto_start(
    client: TestClient,
    workspace_root,
):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["title"] = "Build auth package"
    snapshot["tree_state"]["node_index"][root_id]["description"] = "Parent package"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    _add_child(
        client,
        project_id,
        root_id,
        node_id="child-a",
        title="Auth guard",
        description="Guard routes\n\nWhy now: First gate",
        status="done",
    )
    review_id = _add_review_node(client, project_id, root_id)
    client.app.state.storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:k0",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:k1",
                    "summary": "Guard accepted",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
            ],
            "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )
    _write_confirmed_frame(client, project_id, root_id, "# Parent Frame\nShip auth package\n")

    client.app.state.review_service._codex_client = IntegrationRollupCodexClient(
        summary="Integration output is ready."
    )
    started = client.app.state.review_service.start_review_rollup(project_id, review_id)
    assert started is True

    _wait_for_integration_completion(client, project_id, review_id)

    response = client.get(
        f"/v3/projects/{project_id}/nodes/{review_id}/chat/session",
        params={"thread_role": "audit"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_role"] == "audit"
    assert payload["active_turn_id"] is None
    assert payload["messages"][-1]["role"] == "assistant"
    assert payload["messages"][-1]["status"] == "completed"
    assert "Integration output is ready." in payload["messages"][-1]["content"]

    review_state = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "ready"
    assert review_state["rollup"]["draft"]["summary"] == "Integration output is ready."
    assert review_state["rollup"]["draft"]["sha"].startswith("sha256:")


def test_ask_planning_session_starts_empty_for_child_node(
    client: TestClient,
    workspace_root,
):
    _set_chat_codex_client(client, SlowCheckpointCodexClient())
    project_id, root_id = _setup_project(client, workspace_root)
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["title"] = "Build auth package"
    snapshot["tree_state"]["node_index"][root_id]["description"] = "Parent package"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    _add_child(
        client,
        project_id,
        root_id,
        node_id="child-planning",
        title="Auth guard follow-up",
        description="Handle middleware cleanup\n\nWhy now: Follows the previous checkpoint",
        status="ready",
    )
    review_id = _add_review_node(client, project_id, root_id)
    client.app.state.storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:k0",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:k1",
                    "summary": "Auth middleware accepted",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    response = client.get(
        f"/v3/projects/{project_id}/nodes/child-planning/chat/session",
        params={"thread_role": "ask_planning"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_role"] == "ask_planning"
    assert payload["messages"] == []


def test_review_node_rejects_task_thread_role_pair(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)
    resp = client.get(
        f"/v3/projects/{project_id}/nodes/{review_id}/chat/session",
        params={"thread_role": "ask_planning"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_request"


def test_invalid_thread_role_pair_returns_400_for_message_reset_and_events(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)

    message_resp = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/message",
        params={"thread_role": "integration"},
        json={"content": "hello"},
    )
    assert message_resp.status_code == 400
    assert message_resp.json()["code"] == "invalid_request"

    reset_resp = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/reset",
        params={"thread_role": "integration"},
    )
    assert reset_resp.status_code == 400
    assert reset_resp.json()["code"] == "invalid_request"

    events_resp = client.get(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/events",
        params={"thread_role": "integration"},
    )
    assert events_resp.status_code == 400
    assert events_resp.json()["code"] == "invalid_request"


def test_reset_nonexistent_node(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    resp = client.post(f"/v3/projects/{project_id}/nodes/nonexistent/chat/reset")
    assert resp.status_code == 404


def test_chat_events_nonexistent_node_returns_404(client: TestClient, workspace_root):
    project_id, _ = _setup_project(client, workspace_root)
    response = client.get(f"/v3/projects/{project_id}/nodes/nonexistent/chat/events")
    assert response.status_code == 404


def test_get_session_returns_partial_content_mid_stream(client: TestClient, workspace_root, monkeypatch):
    monkeypatch.setattr(chat_service_module, "_DRAFT_FLUSH_INTERVAL_SEC", 0.01)
    _set_chat_codex_client(client, SlowCheckpointCodexClient())

    project_id, root_id = _setup_project(client, workspace_root)
    response = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/chat/message",
        json={"content": "Hello"},
    )
    assert response.status_code == 200

    deadline = time.time() + 2.0
    streaming_session = None
    while time.time() < deadline:
        session_response = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/chat/session")
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
        session_response = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/chat/session")
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
    codex = ExecutionCodexClient()
    _set_execution_codex_client(client, codex)

    # Initialize git repo so git guardrails pass (can_finish_task gated on git_ready)
    init_git_repo(workspace_root)

    project_id, root_id = _setup_project(client, workspace_root)

    frame_resp = client.put(
        f"/v3/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    assert frame_resp.status_code == 200
    assert client.post(f"/v3/projects/{project_id}/nodes/{root_id}/confirm-frame").status_code == 200

    spec_resp = client.put(
        f"/v3/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    assert spec_resp.status_code == 200
    assert client.post(f"/v3/projects/{project_id}/nodes/{root_id}/confirm-spec").status_code == 200

    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    detail_before = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/detail-state").json()
    assert detail_before["can_finish_task"] is True

    finish_resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert finish_resp.status_code == 200
    payload = finish_resp.json()
    assert payload["execution_started"] is True
    assert payload["shaping_frozen"] is True

    deadline = time.time() + 2.0
    workflow_state = None
    while time.time() < deadline:
        workflow_resp = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/workflow-state")
        assert workflow_resp.status_code == 200
        envelope = workflow_resp.json()
        assert envelope["ok"] is True
        candidate = envelope["data"]
        if candidate.get("executionThreadId"):
            workflow_state = candidate
            break
        time.sleep(0.02)

    assert workflow_state is not None
    assert workflow_state["executionThreadId"] is not None
    assert workflow_state["auditLineageThreadId"] is not None
    assert codex.forked_threads
