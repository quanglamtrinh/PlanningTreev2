from __future__ import annotations

import asyncio
import copy
import json
import threading
import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.ai.ask_prompt_builder import ask_thread_render_tool
from backend.routes.ask import stream_ask_events


class FakeCodexClient:
    def __init__(
        self,
        *,
        block_event: threading.Event | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.block_event = block_event
        self.raise_error = raise_error
        self.started = threading.Event()
        self.available_threads: set[str] = set()
        self.fork_calls: list[dict[str, object]] = []
        self.tool_calls_to_emit: list[tuple[str, dict[str, object]]] = []
        self._planning_counter = 0
        self._ask_counter = 0

    def start_planning_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools,
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        return {"thread_id": thread_id}

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        base_instructions: str | None = None,
        dynamic_tools=None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self.fork_calls.append(
            {
                "source_thread_id": source_thread_id,
                "cwd": cwd,
                "base_instructions": base_instructions,
                "dynamic_tools": dynamic_tools,
                "timeout_sec": timeout_sec,
            }
        )
        if source_thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {source_thread_id}", "rpc_error")
        self._ask_counter += 1
        thread_id = f"ask_{self._ask_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(
        self,
        prompt: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
        on_tool_call=None,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        if callable(on_delta):
            on_delta("hello ")
        if callable(on_tool_call):
            for tool_name, tool_args in self.tool_calls_to_emit:
                on_tool_call(tool_name, copy.deepcopy(tool_args))
        self.started.set()
        if self.block_event is not None:
            self.block_event.wait(timeout=5)
        if self.raise_error is not None:
            raise self.raise_error
        if callable(on_delta):
            on_delta("world")
        return {"stdout": "hello world", "thread_id": thread_id}


def attach_fake_client(client: TestClient, fake_client: FakeCodexClient) -> None:
    client.app.state.ask_service._client = fake_client
    client.app.state.thread_service._codex_client = fake_client


def create_project(
    client: TestClient,
    workspace_root: str,
    fake_client: FakeCodexClient | None = None,
) -> tuple[str, str]:
    attach_fake_client(client, fake_client or FakeCodexClient())
    response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": workspace_root},
    )
    assert response.status_code == 200
    snapshot = client.post(
        "/v1/projects",
        json={"name": "Ask Project", "root_goal": "Ship phase 4"},
    ).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_idle(client: TestClient, project_id: str, node_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/ask/session")
        assert response.status_code == 200
        session = response.json()["session"]
        if session["active_turn_id"] is None:
            return session
        time.sleep(0.02)
    raise AssertionError(f"ask session did not become idle for {node_id}")


def mark_node(client: TestClient, project_id: str, node_id: str, **updates: object) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    node = snapshot["tree_state"]["node_index"][node_id]
    node.update(updates)
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    if "title" in updates or "description" in updates:
        task = client.app.state.storage.node_store.load_task(project_id, node_id)
        if "title" in updates:
            task["title"] = str(updates["title"] or "")
        if "description" in updates:
            task["purpose"] = str(updates["description"] or "")
        client.app.state.storage.node_store.save_task(project_id, node_id, task)
    state_keys = {
        "phase",
        "planning_thread_id",
        "execution_thread_id",
        "planning_thread_forked_from_node",
        "planning_thread_bootstrapped_at",
        "chat_session_id",
    }
    if any(key in updates for key in state_keys):
        state = client.app.state.storage.node_store.load_state(project_id, node_id)
        for key in state_keys:
            if key in updates:
                state[key] = "" if updates[key] is None else updates[key]
        client.app.state.storage.node_store.save_state(project_id, node_id, state)


def attach_active_child(client: TestClient, project_id: str, parent_id: str, child_id: str = "child_1") -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    parent = snapshot["tree_state"]["node_index"][parent_id]
    parent.setdefault("child_ids", []).append(child_id)
    snapshot["tree_state"]["node_index"][child_id] = {
        "node_id": child_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Child",
        "description": "",
        "status": "draft",
        "phase": "planning",
        "node_kind": "original",
        "planning_mode": None,
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(parent.get("child_ids", [])) - 1,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.{len(parent.get('child_ids', []))}",
        "split_metadata": None,
        "chat_session_id": None,
        "planning_thread_id": None,
        "execution_thread_id": None,
        "planning_thread_forked_from_node": None,
        "planning_thread_bootstrapped_at": None,
        "created_at": "2026-03-10T00:00:00Z",
    }
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    client.app.state.storage.node_store.create_node_files(
        project_id,
        child_id,
        task={"title": "Child", "purpose": "", "responsibility": ""},
    )


def test_get_ask_session_returns_default_empty_state(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/ask/session")

    assert response.status_code == 200
    payload = response.json()["session"]
    assert payload["project_id"] == project_id
    assert payload["node_id"] == node_id
    assert payload["event_seq"] == 0
    assert payload["status"] is None
    assert payload["messages"] == []
    assert payload["delta_context_packets"] == []
    assert "thread_id" not in payload
    assert "config" not in payload


def test_send_ask_message_and_complete_turn(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 200
    session = wait_for_idle(client, project_id, node_id)
    assert session["event_seq"] == 4
    assert session["status"] == "idle"
    assert session["messages"][-1]["status"] == "completed"
    assert session["messages"][-1]["content"] == "hello world"
    assert "thread_id" not in session


def test_get_ask_session_keeps_live_turn_active(client: TestClient, workspace_root) -> None:
    release = threading.Event()
    fake_client = FakeCodexClient(block_event=release)
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 200
    assert fake_client.started.wait(timeout=1)

    session_response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/ask/session")
    assert session_response.status_code == 200
    session = session_response.json()["session"]
    assert session["active_turn_id"] is not None
    assert session["messages"][-1]["status"] in {"pending", "streaming"}
    assert session["messages"][-1]["error"] is None

    release.set()
    completed = wait_for_idle(client, project_id, node_id)
    assert completed["messages"][-1]["status"] == "completed"
    assert completed["messages"][-1]["content"] == "hello world"


class _FakeStreamRequest:
    def __init__(self, app) -> None:
        self.app = app
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


def test_ask_events_stream_sends_sse_payload(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    broker = client.app.state.ask_event_broker
    payload = {
        "type": "ask_assistant_delta",
        "event_seq": 4,
        "message_id": "msg_1",
        "delta": "hi",
        "content": "hi",
        "updated_at": "2026-03-11T00:00:00Z",
    }
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_ask_events(project_id, node_id, request)
        chunk_task = asyncio.create_task(anext(response.body_iterator))

        deadline = time.time() + 1
        while time.time() < deadline:
            if broker._queues.get((project_id, node_id), set()):
                break
            await asyncio.sleep(0.01)

        broker.publish(project_id, node_id, payload)
        chunk = await asyncio.wait_for(chunk_task, timeout=1)
        request._disconnected = True
        await response.body_iterator.aclose()
        return response, chunk

    response, chunk = asyncio.run(collect_chunk())

    assert response.status_code == 200
    assert "event: message" in chunk
    assert f"data: {json.dumps(payload, ensure_ascii=True)}" in chunk


def test_ask_route_returns_404_for_missing_node(client: TestClient, workspace_root) -> None:
    project_id, _ = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/missing/ask/session")

    assert response.status_code == 404
    assert response.json()["code"] == "node_not_found"


def test_ask_rejects_concurrent_turns(client: TestClient, workspace_root) -> None:
    release = threading.Event()
    fake_client = FakeCodexClient(block_event=release)
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    first = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )
    assert first.status_code == 200
    assert fake_client.started.wait(timeout=1)

    second = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "again"},
    )

    assert second.status_code == 409
    assert second.json()["code"] == "ask_turn_already_active"

    release.set()
    wait_for_idle(client, project_id, node_id)


def test_ask_rejects_when_planning_active(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    client.app.state.storage.thread_store.set_planning_status(
        project_id,
        node_id,
        status="active",
        active_turn_id="planturn_1",
    )

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ask_blocked_by_planning_active"


def test_ask_rejects_done_node(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    mark_node(client, project_id, node_id, status="done")

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ask_thread_read_only"


def test_ask_rejects_superseded_node(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    mark_node(client, project_id, node_id, is_superseded=True)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ask_thread_read_only"


def test_reset_ask_session_clears_messages_and_hides_thread_id(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    send = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )
    assert send.status_code == 200
    wait_for_idle(client, project_id, node_id)

    reset = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/reset")

    assert reset.status_code == 200
    session = reset.json()["session"]
    assert session["messages"] == []
    assert session["status"] is None
    assert "thread_id" not in session


def test_get_ask_conversation_v2_normalizes_visible_transcript(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    send = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "hello"},
    )
    assert send.status_code == 200
    wait_for_idle(client, project_id, node_id)

    response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/ask")

    assert response.status_code == 200
    conversation = response.json()["conversation"]
    assert conversation["record"]["thread_type"] == "ask"
    assert conversation["record"]["current_runtime_mode"] == "ask"
    assert conversation["record"]["status"] == "completed"
    assert conversation["record"]["event_seq"] == 12
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert conversation["messages"][0]["parts"][0]["part_type"] == "user_text"
    assert conversation["messages"][1]["parts"][0]["part_type"] == "assistant_text"
    assert conversation["messages"][1]["parts"][0]["payload"]["text"] == "hello world"


def test_ask_v2_send_and_reset_preserve_conversation_identity(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    first = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/ask")
    assert first.status_code == 200
    first_conversation = first.json()["conversation"]

    send = client.post(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/ask/send",
        json={"content": "hello"},
    )
    assert send.status_code == 202
    accepted = send.json()
    wait_for_idle(client, project_id, node_id)

    reset = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/reset")
    assert reset.status_code == 200

    after_reset = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/ask")
    assert after_reset.status_code == 200
    reset_conversation = after_reset.json()["conversation"]

    assert accepted["conversation_id"] == first_conversation["record"]["conversation_id"]
    assert reset_conversation["record"]["conversation_id"] == first_conversation["record"]["conversation_id"]
    assert reset_conversation["record"]["event_seq"] > first_conversation["record"]["event_seq"]
    assert reset_conversation["messages"] == []
    assert reset_conversation["record"]["status"] == "idle"


def test_list_packets_returns_empty_for_new_node(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets")

    assert response.status_code == 200
    assert response.json() == {"packets": []}


def test_create_packet_via_post(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need more detail.", "source_message_ids": ["msg_1"]},
    )

    assert response.status_code == 200
    packet = response.json()["packet"]
    assert packet["suggested_by"] == "user"
    assert packet["source_message_ids"] == ["msg_1"]
    packets = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets").json()["packets"]
    assert [item["packet_id"] for item in packets] == [packet["packet_id"]]


def test_create_packet_rejects_when_planning_active(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    client.app.state.storage.thread_store.set_planning_status(
        project_id,
        node_id,
        status="active",
        active_turn_id="planturn_1",
    )

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need more detail."},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ask_blocked_by_planning_active"


def test_create_packet_rejects_after_split(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    attach_active_child(client, project_id, node_id)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need more detail."},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "packet_mutation_blocked_by_split"


def test_approve_packet_via_post(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need more detail."},
    ).json()["packet"]

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve")

    assert response.status_code == 200
    assert response.json()["packet"]["status"] == "approved"


def test_reject_approved_packet_via_post(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need more detail."},
    ).json()["packet"]
    approved = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve"
    ).json()["packet"]

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{approved['packet_id']}/reject")

    assert response.status_code == 200
    assert response.json()["packet"]["status"] == "rejected"
    assert response.json()["packet"]["status_reason"] == "Rejected by user"


def test_approve_missing_packet_returns_404(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/missing/approve")

    assert response.status_code == 404
    assert response.json()["code"] == "packet_not_found"


def test_agent_tool_call_creates_packet_during_turn(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    fake_client.tool_calls_to_emit = [
        (
            "emit_render_data",
            {
                "kind": "delta_context_suggestion",
                "payload": {
                    "summary": "Dependency",
                    "context_text": "Need stable upstream API.",
                },
            },
        )
    ]
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "What are the risks?"},
    )

    assert response.status_code == 200
    session = wait_for_idle(client, project_id, node_id)
    packet = session["delta_context_packets"][0]
    assert packet["summary"] == "Dependency"
    assert packet["source_message_ids"] == [
        response.json()["user_message_id"],
        response.json()["assistant_message_id"],
    ]
    assert fake_client.fork_calls[0]["dynamic_tools"] == [ask_thread_render_tool()]


def test_agent_tool_call_ignored_after_split(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    fake_client.tool_calls_to_emit = [
        (
            "emit_render_data",
            {
                "kind": "delta_context_suggestion",
                "payload": {
                    "summary": "Dependency",
                    "context_text": "Need stable upstream API.",
                },
            },
        )
    ]
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    attach_active_child(client, project_id, node_id)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
        json={"content": "What are the risks?"},
    )

    assert response.status_code == 200
    session = wait_for_idle(client, project_id, node_id)
    assert session["delta_context_packets"] == []


def test_packet_events_published_on_sse_for_manual_create(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_ask_events(project_id, node_id, request)
        chunk_task = asyncio.create_task(anext(response.body_iterator))
        deadline = time.time() + 1
        while time.time() < deadline:
            if client.app.state.ask_event_broker._queues.get((project_id, node_id), set()):
                break
            await asyncio.sleep(0.01)

        create_response = client.post(
            f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
            json={"summary": "Scope", "context_text": "Need more detail."},
        )
        assert create_response.status_code == 200
        chunk = await asyncio.wait_for(chunk_task, timeout=1)
        request._disconnected = True
        await response.body_iterator.aclose()
        return response, chunk

    response, chunk = asyncio.run(collect_chunk())

    assert response.status_code == 200
    assert '"type": "ask_delta_context_suggested"' in chunk


def test_packet_events_published_on_sse_for_agent_suggestion(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    fake_client.tool_calls_to_emit = [
        (
            "emit_render_data",
            {
                "kind": "delta_context_suggestion",
                "payload": {
                    "summary": "Dependency",
                    "context_text": "Need stable upstream API.",
                },
            },
        )
    ]
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_ask_events(project_id, node_id, request)
        chunk_task = asyncio.create_task(anext(response.body_iterator))

        deadline = time.time() + 1
        while time.time() < deadline:
            if client.app.state.ask_event_broker._queues.get((project_id, node_id), set()):
                break
            await asyncio.sleep(0.01)

        create_response = client.post(
            f"/v1/projects/{project_id}/nodes/{node_id}/ask/messages",
            json={"content": "What are the risks?"},
        )
        assert create_response.status_code == 200
        first_chunk = await asyncio.wait_for(chunk_task, timeout=1)
        chunk = first_chunk
        deadline = time.time() + 2
        while '"type": "ask_delta_context_suggested"' not in chunk and time.time() < deadline:
            next_chunk = await asyncio.wait_for(anext(response.body_iterator), timeout=1)
            chunk += next_chunk
        request._disconnected = True
        await response.body_iterator.aclose()
        return response, chunk

    response, chunk = asyncio.run(collect_chunk())

    assert response.status_code == 200
    assert '"type": "ask_delta_context_suggested"' in chunk


def test_merge_packet_via_post(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need stable API."},
    ).json()["packet"]
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve")

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/merge")

    assert response.status_code == 200
    merged = response.json()["packet"]
    assert merged["status"] == "merged"
    assert merged["merged_at"] is not None


def test_merge_creates_context_merge_planning_turn(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need stable API."},
    ).json()["packet"]
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve")

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/merge")

    assert response.status_code == 200
    planning_turns = client.app.state.storage.thread_store.get_planning_turns(project_id, node_id)
    merge_turn = planning_turns[-1]
    assert merge_turn["role"] == "context_merge"
    assert merge_turn["packet_id"] == packet["packet_id"]
    assert merge_turn["content"] == "Need stable API."
    assert merge_turn["summary"] == "Scope"


def test_merge_rejects_unapproved_packet(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need stable API."},
    ).json()["packet"]

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/merge")

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_packet_transition"


def test_merge_rejects_after_split(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need stable API."},
    ).json()["packet"]
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve")
    attach_active_child(client, project_id, node_id)

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/merge")

    assert response.status_code == 409
    assert response.json()["code"] == "merge_blocked_by_split"


def test_merge_missing_packet_returns_404(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/missing/merge")

    assert response.status_code == 404
    assert response.json()["code"] == "packet_not_found"


def test_merge_returns_503_when_planning_thread_is_unavailable(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    packet = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets",
        json={"summary": "Scope", "context_text": "Need stable API."},
    ).json()["packet"]
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/approve")
    mark_node(client, project_id, node_id, planning_thread_id="planning_stale")

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/ask/packets/{packet['packet_id']}/merge")

    assert response.status_code == 503
    assert response.json()["code"] == "merge_planning_thread_unavailable"
