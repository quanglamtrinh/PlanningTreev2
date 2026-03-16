from __future__ import annotations

import asyncio
import json
import threading
import time

from fastapi.testclient import TestClient

import backend.main as backend_main
from backend.ai.codex_client import RuntimeRequestRecord
from backend.routes.conversation import (
    stream_execution_conversation_events,
    stream_planning_conversation_events,
)
from backend.services.conversation_gateway import _LiveConversationState
from backend.tests.integration.test_chat_api import FakeCodexClient, attach_fake_client


class FakeConversationClient:
    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        plan_deltas: list[dict[str, object]] | None = None,
        tool_calls: list[dict[str, object]] | None = None,
        runtime_requests: list[dict[str, object]] | None = None,
        request_resolutions: list[dict[str, object]] | None = None,
        final_text: str | None = None,
        final_plan_item: dict[str, object] | None = None,
        block_event: threading.Event | None = None,
        raise_error: Exception | None = None,
        returned_thread_id: str = "thread_exec_1",
    ) -> None:
        self.deltas = list(deltas or [])
        self.plan_deltas = list(plan_deltas or [])
        self.tool_calls = list(tool_calls or [])
        self.runtime_requests = [dict(item) for item in (runtime_requests or [])]
        self.request_resolutions = [dict(item) for item in (request_resolutions or [])]
        self.final_text = final_text
        self.final_plan_item = dict(final_plan_item) if isinstance(final_plan_item, dict) else None
        self.block_event = block_event
        self.raise_error = raise_error
        self.returned_thread_id = returned_thread_id
        self.started = threading.Event()
        self.calls: list[dict[str, object]] = []
        self.pending_requests: dict[str, dict[str, object]] = {}
        self.resolved_answers: dict[str, dict[str, object]] = {}

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
        on_tool_call=None,
        on_plan_delta=None,
        on_request_user_input=None,
        on_request_resolved=None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "prompt": prompt,
                "thread_id": thread_id,
                "timeout_sec": timeout_sec,
                "cwd": cwd,
                "writable_roots": writable_roots,
            }
        )
        self.started.set()
        if self.block_event is not None:
            self.block_event.wait(timeout=5)
        if self.raise_error is not None:
            raise self.raise_error
        if callable(on_tool_call):
            for tool_call in self.tool_calls:
                on_tool_call(
                    str(tool_call.get("tool_name") or ""),
                    tool_call.get("arguments")
                    if isinstance(tool_call.get("arguments"), dict)
                    else {},
                )
        if callable(on_plan_delta):
            for plan_delta in self.plan_deltas:
                on_plan_delta(
                    str(plan_delta.get("delta") or ""),
                    {
                        "id": str(plan_delta.get("id") or ""),
                        "turn_id": str(plan_delta.get("turn_id") or ""),
                        "thread_id": str(plan_delta.get("thread_id") or self.returned_thread_id),
                    },
                )
        if callable(on_request_user_input):
            for request in self.runtime_requests:
                request_id = str(request.get("request_id") or f"req_{len(self.pending_requests) + 1}")
                wait_for_resolution = bool(request.get("wait_for_resolution"))
                wait_event = threading.Event() if wait_for_resolution else None
                normalized_request = {
                    "request_id": request_id,
                    "thread_id": str(request.get("thread_id") or self.returned_thread_id),
                    "turn_id": str(request.get("turn_id") or ""),
                    "item_id": str(request.get("item_id") or f"item_{request_id}"),
                    "status": str(request.get("status") or "pending"),
                    "created_at": str(request.get("created_at") or "2026-03-15T00:00:02Z"),
                    "questions": list(request.get("questions") or []),
                    "title": request.get("title"),
                    "summary": request.get("summary"),
                    "prompt": request.get("prompt"),
                }
                self.pending_requests[request_id] = {
                    "payload": normalized_request,
                    "wait_event": wait_event,
                }
                on_request_user_input(normalized_request)
                if wait_event is not None:
                    wait_event.wait(timeout=5)
        if callable(on_request_resolved):
            for resolution in self.request_resolutions:
                on_request_resolved(
                    {
                        "request_id": str(resolution.get("request_id") or ""),
                        "thread_id": str(resolution.get("thread_id") or self.returned_thread_id),
                        "turn_id": str(resolution.get("turn_id") or ""),
                        "status": str(resolution.get("status") or "resolved"),
                        "resolved_at": str(resolution.get("resolved_at") or "2026-03-15T00:00:03Z"),
                    }
                )
        if callable(on_delta):
            for delta in self.deltas:
                on_delta(delta)
        return {
            "stdout": self.final_text if self.final_text is not None else "".join(self.deltas),
            "thread_id": self.returned_thread_id,
            "tool_calls": list(self.tool_calls),
            "final_plan_item": dict(self.final_plan_item) if self.final_plan_item is not None else None,
        }

    def stop(self) -> None:
        return None

    def resolve_runtime_request_user_input(
        self,
        request_id: str,
        *,
        answers: dict[str, object],
    ) -> RuntimeRequestRecord | None:
        pending = self.pending_requests.get(request_id)
        if pending is None:
            return None
        payload = pending["payload"]
        self.resolved_answers[request_id] = {"answers": answers}
        wait_event = pending.get("wait_event")
        if isinstance(wait_event, threading.Event):
            wait_event.set()
        return RuntimeRequestRecord(
            request_id=request_id,
            rpc_request_id=request_id,
            thread_id=str(payload.get("thread_id") or self.returned_thread_id),
            turn_id=str(payload.get("turn_id") or ""),
            node_id=None,
            item_id=str(payload.get("item_id") or f"item_{request_id}"),
            prompt_payload={},
            answer_payload={"answers": answers},
            status="resolved",
            resolved_at="2026-03-15T00:00:05Z",
        )


class FakeConversationClientFactory:
    def __init__(self, clients: list[FakeConversationClient] | None = None) -> None:
        self._clients = list(clients or [])
        self.created: list[tuple[str, FakeConversationClient]] = []
        self._lock = threading.Lock()

    def __call__(self, workspace_root: str) -> FakeConversationClient:
        with self._lock:
            client = self._clients.pop(0) if self._clients else FakeConversationClient()
            self.created.append((workspace_root, client))
            return client


def attach_session_client_factory(client: TestClient, factory) -> None:
    client.app.state.codex_session_manager._client_factory = factory


def create_project(client: TestClient, workspace_root: str) -> tuple[str, str]:
    attach_fake_client(client, FakeCodexClient())
    response = client.patch("/v1/settings/workspace", json={"base_workspace_root": workspace_root})
    assert response.status_code == 200
    snapshot = client.post("/v1/projects", json={"name": "Chat Project", "root_goal": "Ship phase 4"}).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def create_child_node(client: TestClient, project_id: str, parent_node_id: str) -> str:
    snapshot = client.app.state.node_service.create_child(project_id, parent_node_id)
    return snapshot["tree_state"]["active_node_id"]


def set_node_phase(client: TestClient, project_id: str, node_id: str, phase: str) -> None:
    storage = client.app.state.storage
    tree_service = client.app.state.tree_service
    snapshot = storage.project_store.load_snapshot(project_id)
    tree_service.node_index(snapshot)[node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def wait_for_conversation(
    client: TestClient,
    project_id: str,
    node_id: str,
    predicate,
    timeout: float = 2.0,
) -> dict[str, object]:
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution")
        assert response.status_code == 200
        last_payload = response.json()["conversation"]
        if predicate(last_payload):
            return last_payload
        time.sleep(0.02)
    raise AssertionError(f"conversation did not reach the expected state: {last_payload}")


class _FakeStreamRequest:
    def __init__(self, app) -> None:
        self.app = app
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


def _start_request_thread(action):
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["response"] = action()
        except BaseException as exc:  # pragma: no cover - surfaced in caller
            error["exc"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread, result, error


async def collect_route_events(
    client: TestClient,
    *,
    project_id: str,
    conversation_id: str,
    node_id: str,
    action,
    terminal_statuses: set[str],
    after_event_seq: int = 0,
    expected_stream_id: str | None = None,
) -> tuple[object, list[dict[str, object]]]:
    broker = client.app.state.conversation_event_broker
    events: list[dict[str, object]] = []
    request = _FakeStreamRequest(client.app)
    response = await stream_execution_conversation_events(
        request,
        project_id,
        node_id,
        after_event_seq=after_event_seq,
        expected_stream_id=expected_stream_id,
    )
    pending_chunk = asyncio.create_task(anext(response.body_iterator))
    deadline = time.time() + 2
    while time.time() < deadline:
        if broker._queues.get((project_id, conversation_id), set()):
            break
        await asyncio.sleep(0.01)
    else:
        request._disconnected = True
        await response.body_iterator.aclose()
        raise AssertionError("conversation event stream did not subscribe in time")

    thread, result, error = _start_request_thread(action)
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                chunk = await asyncio.wait_for(pending_chunk, timeout=max(0.01, deadline - time.time()))
            except asyncio.TimeoutError as exc:  # pragma: no cover - surfaced in caller
                raise AssertionError("conversation event stream did not produce a terminal event in time") from exc
            except StopAsyncIteration:
                break
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
            if text.startswith("data: "):
                payload = json.loads(text[6:])
                events.append(payload)
                if payload.get("event_type") == "completion_status":
                    status = str(payload.get("payload", {}).get("status") or "")
                    if status in terminal_statuses:
                        break
            pending_chunk = asyncio.create_task(anext(response.body_iterator))
    finally:
        request._disconnected = True
        await response.body_iterator.aclose()
    thread.join(timeout=2)
    if thread.is_alive():
        raise AssertionError("conversation request thread did not finish in time")
    if "exc" in error:
        raise error["exc"]
    return result.get("response"), events


async def collect_broker_events(
    client: TestClient,
    *,
    project_id: str,
    conversation_id: str,
    action,
    terminal_statuses: set[str],
) -> tuple[object, list[dict[str, object]]]:
    broker = client.app.state.conversation_event_broker
    queue = broker.subscribe(project_id, conversation_id)
    thread, result, error = _start_request_thread(action)
    events: list[dict[str, object]] = []
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            event = await asyncio.wait_for(queue.get(), timeout=max(0.01, deadline - time.time()))
            events.append(event)
            if event.get("event_type") == "completion_status":
                status = str(event.get("payload", {}).get("status") or "")
                if status in terminal_statuses:
                    break
    finally:
        broker.unsubscribe(project_id, conversation_id, queue)
    thread.join(timeout=2)
    if thread.is_alive():
        raise AssertionError("conversation request thread did not finish in time")
    if "exc" in error:
        raise error["exc"]
    return result.get("response"), events


def test_get_execution_conversation_returns_canonical_empty_snapshot(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    first = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution")
    second = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution")

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()["conversation"]
    second_payload = second.json()["conversation"]
    assert first_payload["record"]["conversation_id"] == second_payload["record"]["conversation_id"]
    assert first_payload["record"]["event_seq"] == 0
    assert first_payload["record"]["active_stream_id"] is None
    assert first_payload["messages"] == []


def test_execution_events_route_streams_sse_payload(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    broker = client.app.state.conversation_event_broker
    payload = {
        "event_type": "message_created",
        "conversation_id": conversation_id,
        "stream_id": "stream_1",
        "event_seq": 1,
        "created_at": "2026-03-15T00:00:00Z",
        "payload": {"message": {"message_id": "msg_1"}},
    }
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_execution_conversation_events(request, project_id, node_id, after_event_seq=0)
        chunk_task = asyncio.create_task(anext(response.body_iterator))
        deadline = time.time() + 1
        while time.time() < deadline:
            if broker._queues.get((project_id, conversation_id), set()):
                break
            await asyncio.sleep(0.01)
        broker.publish(project_id, conversation_id, payload)
        chunk = await asyncio.wait_for(chunk_task, timeout=1)
        request._disconnected = True
        await response.body_iterator.aclose()
        return response, chunk

    response, chunk = asyncio.run(collect_chunk())

    assert response.status_code == 200
    assert "event: message" in chunk
    assert f"data: {json.dumps(payload, ensure_ascii=True)}" in chunk


def test_get_planning_conversation_route_normalizes_visible_planning_transcript(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    client.app.state.storage.thread_store.replace_planning_turns(
        project_id,
        node_id,
        [
            {
                "turn_id": "turn_split_1",
                "role": "user",
                "content": "Split this node into slices.",
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:01Z",
            },
            {
                "turn_id": "turn_split_1",
                "role": "tool_call",
                "tool_name": "emit_render_data",
                "arguments": {
                    "kind": "split_result",
                    "payload": {
                        "subtasks": [
                            {"order": 1, "prompt": "Setup repo"},
                            {"order": 2, "prompt": "Wire planning host"},
                        ]
                    },
                },
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:02Z",
            },
            {
                "turn_id": "turn_split_1",
                "role": "assistant",
                "content": "",
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:03Z",
            },
        ],
    )
    client.app.state.storage.thread_store.set_planning_status(
        project_id,
        node_id,
        thread_id="planning_thread_1",
        status="idle",
        active_turn_id=None,
    )

    response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/planning")

    assert response.status_code == 200
    payload = response.json()["conversation"]
    assert payload["record"]["thread_type"] == "planning"
    assert payload["record"]["app_server_thread_id"] == "planning_thread_1"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["parts"][0]["payload"]["text"] == "Split completed. Created 2 child tasks."
    assert payload["messages"][1]["parts"][1]["part_type"] == "tool_call"


def test_planning_events_route_translates_planning_broker_events_to_normalized_sse(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    planning_state = client.app.state.storage.thread_store.get_or_create_planning_conversation_state(
        project_id,
        node_id,
    )
    conversation_id = str(planning_state["conversation_id"])
    broker = client.app.state.planning_event_broker
    request = _FakeStreamRequest(client.app)

    async def collect_chunks() -> list[str]:
        response = await stream_planning_conversation_events(
            request,
            project_id,
            node_id,
            after_event_seq=0,
            expected_stream_id=None,
        )
        chunk_task = asyncio.create_task(anext(response.body_iterator))
        deadline = time.time() + 1
        while time.time() < deadline:
            if broker._queues.get((project_id, node_id), set()):
                break
            await asyncio.sleep(0.01)
        else:
            request._disconnected = True
            await response.body_iterator.aclose()
            raise AssertionError("planning event stream did not subscribe in time")
        broker.publish(
            project_id,
            node_id,
            {
                "type": "planning_turn_started",
                "node_id": node_id,
                "turn_id": "turn_1",
                "mode": "slice",
                "timestamp": "2026-03-15T00:00:01Z",
                "conversation_id": conversation_id,
                "stream_id": "planning_stream:turn_1",
                "user_content": "Split this node into slices.",
                "user_event_seq": 1,
                "assistant_event_seq": 2,
            },
        )

        chunks: list[str] = []
        try:
            for _ in range(2):
                chunk = await asyncio.wait_for(chunk_task, timeout=1)
                text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                chunks.append(text)
                chunk_task = asyncio.create_task(anext(response.body_iterator))
        finally:
            request._disconnected = True
            await response.body_iterator.aclose()
        return chunks

    chunks = asyncio.run(collect_chunks())

    assert any('"event_type": "message_created"' in chunk for chunk in chunks)
    assert any(f'"conversation_id": "{conversation_id}"' in chunk for chunk in chunks)
    assert any('"role": "user"' in chunk for chunk in chunks)
    assert any('"role": "assistant"' in chunk for chunk in chunks)


def test_get_post_send_get_again_keeps_same_conversation_id_and_live_enrichment(
    client: TestClient,
    workspace_root,
) -> None:
    release = threading.Event()
    fake_client = FakeConversationClient(block_event=release, final_text="")
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")

    before = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution")
    assert before.status_code == 200
    conversation_id = before.json()["conversation"]["record"]["conversation_id"]

    accepted = client.post(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
        json={"content": "hello"},
    )

    assert accepted.status_code == 202
    assert fake_client.started.wait(timeout=1)

    session = client.app.state.codex_session_manager.get_session(project_id)
    gateway = client.app.state.conversation_gateway
    assert session is not None
    with session.lock:
        gateway._live_state[(project_id, conversation_id)] = _LiveConversationState(
            event_seq=7,
            assistant_text="memory only live text",
        )

    during = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution")
    assert during.status_code == 200
    payload = during.json()["conversation"]
    assert payload["record"]["conversation_id"] == conversation_id
    assert payload["record"]["active_stream_id"] == accepted.json()["stream_id"]
    assert payload["record"]["event_seq"] == 7
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["parts"][0]["payload"]["text"] == ""

    release.set()
    wait_for_conversation(
        client,
        project_id,
        node_id,
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )


def test_execution_conversation_success_streams_in_order_and_persists_normalized_messages(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeConversationClient(deltas=["hello ", "world"], final_text="hello world")
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    accepted, events = asyncio.run(
        collect_broker_events(
            client,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
                json={"content": "hello"},
            ),
            terminal_statuses={"completed"},
        )
    )

    assert accepted.status_code == 202
    client.app.state.conversation_gateway.flush_persistence()

    event_types = [event["event_type"] for event in events]
    event_seqs = [int(event["event_seq"]) for event in events]
    assistant_text_events = [
        event for event in events if event["event_type"] in {"assistant_text_delta", "assistant_text_final"}
    ]

    assert event_types[0:2] == ["message_created", "message_created"]
    assert event_types[-2:] == ["assistant_text_final", "completion_status"]
    assert "assistant_text_delta" in event_types
    assert event_seqs == [1, 2, 3, 4, 5, 6]
    assert event_seqs == sorted(event_seqs)
    assert len(set(event_seqs)) == len(event_seqs)
    assert {event["conversation_id"] for event in events} == {conversation_id}
    assert {event["stream_id"] for event in events} == {accepted.json()["stream_id"]}
    assert events[0]["payload"]["message"]["role"] == "user"
    assert events[1]["payload"]["message"]["role"] == "assistant"
    assert events[0]["message_id"] == accepted.json()["user_message_id"]
    assert events[1]["message_id"] == accepted.json()["assistant_message_id"]
    assert events[-1]["message_id"] == accepted.json()["assistant_message_id"]
    assert {event["message_id"] for event in assistant_text_events} == {accepted.json()["assistant_message_id"]}
    assert {event["item_id"] for event in assistant_text_events} == {accepted.json()["assistant_text_part_id"]}
    assert events[-1]["payload"]["status"] == "completed"

    persisted = client.app.state.storage.conversation_store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    assert persisted["record"]["status"] == "completed"
    assert persisted["record"]["active_stream_id"] is None
    assert persisted["record"]["app_server_thread_id"] == "thread_exec_1"
    assert [message["role"] for message in persisted["messages"]] == ["user", "assistant"]
    assert persisted["messages"][1]["parts"][0]["payload"]["text"] == "hello world"


def test_execution_conversation_persists_tool_call_parts_and_streams_passive_tool_events(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeConversationClient(
        tool_calls=[
            {
                "tool_name": "emit_render_data",
                "arguments": {
                    "kind": "split_result",
                    "payload": {
                        "subtasks": [
                            {"order": 1, "prompt": "Setup repo"},
                        ]
                    },
                },
            }
        ],
        final_text="Rendered a structured split result.",
    )
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    accepted, events = asyncio.run(
        collect_broker_events(
            client,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
                json={"content": "render split"},
            ),
            terminal_statuses={"completed"},
        )
    )

    assert accepted.status_code == 202
    client.app.state.conversation_gateway.flush_persistence()

    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "message_created",
        "message_created",
        "tool_call_start",
        "assistant_text_final",
        "completion_status",
    ]
    assert events[2]["payload"]["tool_name"] == "emit_render_data"
    assert events[2]["item_id"] == f"{accepted.json()['assistant_message_id']}:tool_call:0"

    persisted = client.app.state.storage.conversation_store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    assert persisted["messages"][1]["parts"][1]["part_type"] == "tool_call"
    assert persisted["messages"][1]["parts"][1]["payload"]["tool_call_id"] == persisted["messages"][1]["parts"][1]["part_id"]
    assert persisted["messages"][1]["parts"][1]["payload"]["tool_name"] == "emit_render_data"
    assert persisted["messages"][1]["parts"][1]["payload"]["arguments"]["kind"] == "split_result"


def test_execution_conversation_persists_plan_block_parts_and_streams_passive_plan_events(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeConversationClient(
        plan_deltas=[
            {"id": "plan_1", "turn_id": "turn_1", "delta": "Draft "},
            {"id": "plan_1", "turn_id": "turn_1", "delta": "plan"},
        ],
        final_plan_item={
            "id": "plan_1",
            "text": "Final plan",
            "turn_id": "turn_1",
            "thread_id": "thread_exec_1",
        },
        final_text="Plan is ready.",
    )
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    accepted, events = asyncio.run(
        collect_broker_events(
            client,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
                json={"content": "plan this"},
            ),
            terminal_statuses={"completed"},
        )
    )

    assert accepted.status_code == 202
    client.app.state.conversation_gateway.flush_persistence()

    plan_events = [event for event in events if event["event_type"] == "plan_block"]
    assert [event["event_type"] for event in events] == [
        "message_created",
        "message_created",
        "plan_block",
        "plan_block",
        "plan_block",
        "assistant_text_final",
        "completion_status",
    ]
    assert {event["item_id"] for event in plan_events} == {
        f"{accepted.json()['assistant_message_id']}:plan_block:plan_1"
    }

    persisted = client.app.state.storage.conversation_store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    assert [part["part_type"] for part in persisted["messages"][1]["parts"]] == ["assistant_text", "plan_block"]
    assert persisted["messages"][1]["parts"][1]["part_id"] == f"{accepted.json()['assistant_message_id']}:plan_block:plan_1"
    assert persisted["messages"][1]["parts"][1]["payload"]["text"] == "Final plan"


def test_execution_conversation_resolves_runtime_input_requests_through_v2_route(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeConversationClient(
        runtime_requests=[
            {
                "request_id": "req_exec_3",
                "turn_id": "turn_1",
                "item_id": "item_req_3",
                "wait_for_resolution": True,
                "questions": [
                    {
                        "id": "brand_direction",
                        "header": "Brand direction",
                        "question": "What visual direction should we use?",
                        "options": [
                            {"label": "Editorial", "description": "Structured and dense."},
                        ],
                    }
                ],
            }
        ],
        final_text="Continuing after input.",
    )
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]

    async def run() -> tuple[object, object, list[dict[str, object]]]:
        broker = client.app.state.conversation_event_broker
        queue = broker.subscribe(project_id, conversation_id)
        send_thread, send_result, send_error = _start_request_thread(
            lambda: client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
                json={"content": "continue"},
            )
        )
        events: list[dict[str, object]] = []
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=1)
                events.append(event)
                if event["event_type"] == "request_user_input":
                    break

            resolve_response = client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/requests/req_exec_3/resolve",
                json={
                    "request_kind": "user_input",
                    "thread_id": "thread_exec_1",
                    "turn_id": "turn_1",
                    "answers": {"brand_direction": {"answers": ["Editorial"]}},
                },
            )

            deadline = time.time() + 3
            seen_required = {"completion_status": False, "request_resolved": False, "user_input_resolved": False}
            while time.time() < deadline:
                event = await asyncio.wait_for(queue.get(), timeout=max(0.01, deadline - time.time()))
                events.append(event)
                event_type = str(event.get("event_type") or "")
                if event_type in seen_required:
                    seen_required[event_type] = True
                if all(seen_required.values()):
                    break
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

        send_thread.join(timeout=2)
        if send_thread.is_alive():
            raise AssertionError("execution send thread did not finish in time")
        if "exc" in send_error:
            raise send_error["exc"]
        return send_result.get("response"), resolve_response, events

    accepted, resolved, events = asyncio.run(run())

    assert accepted.status_code == 202
    assert resolved.status_code == 200
    assert resolved.json() == {"status": "resolved"}
    event_types = [event["event_type"] for event in events]
    event_seqs = [int(event["event_seq"]) for event in events]
    assert event_types[:3] == [
        "message_created",
        "message_created",
        "request_user_input",
    ]
    assert event_types.count("request_resolved") == 1
    assert event_types.count("user_input_resolved") == 1
    assert event_types.count("assistant_text_final") == 1
    assert event_types.count("completion_status") == 1
    assert event_seqs == sorted(event_seqs)

    persisted = client.app.state.storage.conversation_store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    request_message = next(message for message in persisted["messages"] if message["message_id"] == "request_message:req_exec_3")
    response_message = next(
        message for message in persisted["messages"] if message["message_id"] == "request_response:req_exec_3"
    )
    assert request_message["parts"][0]["payload"]["resolution_state"] == "resolved"
    assert response_message["role"] == "user"
    assert response_message["parts"][0]["part_type"] == "user_input_response"
    assert response_message["parts"][0]["payload"]["answers"] == {
        "brand_direction": {"answers": ["Editorial"]}
    }


def test_execution_conversation_error_path_emits_completion_only_and_clears_ownership(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeConversationClient(raise_error=RuntimeError("boom"))
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    accepted, events = asyncio.run(
        collect_broker_events(
            client,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: client.post(
                f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
                json={"content": "hello"},
            ),
            terminal_statuses={"error"},
        )
    )

    assert accepted.status_code == 202
    client.app.state.conversation_gateway.flush_persistence()

    event_types = [event["event_type"] for event in events]
    assert event_types == ["message_created", "message_created", "completion_status"]
    assert events[-1]["payload"]["status"] == "error"
    persisted = client.app.state.storage.conversation_store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    assert persisted["record"]["status"] == "error"
    assert persisted["record"]["active_stream_id"] is None
    assert persisted["messages"][1]["status"] == "error"


def test_same_project_nodes_reuse_one_project_scoped_session(client: TestClient, workspace_root) -> None:
    factory = FakeConversationClientFactory(
        [
            FakeConversationClient(final_text="root"),
            FakeConversationClient(final_text="child"),
        ]
    )
    attach_session_client_factory(client, factory)
    project_id, root_id = create_project(client, str(workspace_root))
    child_id = create_child_node(client, project_id, root_id)
    set_node_phase(client, project_id, root_id, "executing")
    set_node_phase(client, project_id, child_id, "executing")

    first = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/conversations/execution/send",
        json={"content": "hello root"},
    )
    second = client.post(
        f"/v2/projects/{project_id}/nodes/{child_id}/conversations/execution/send",
        json={"content": "hello child"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    wait_for_conversation(client, project_id, root_id, lambda item: item["record"]["status"] == "completed")
    wait_for_conversation(client, project_id, child_id, lambda item: item["record"]["status"] == "completed")
    assert len(factory.created) == 1
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    assert factory.created[0][1].calls[0]["cwd"] == snapshot["project"]["project_workspace_root"]
    assert len(factory.created[0][1].calls) == 2


def test_different_projects_get_isolated_project_sessions(client: TestClient, workspace_root) -> None:
    factory = FakeConversationClientFactory(
        [
            FakeConversationClient(final_text="one"),
            FakeConversationClient(final_text="two"),
        ]
    )
    attach_session_client_factory(client, factory)
    project_one, node_one = create_project(client, str(workspace_root))
    project_two, node_two = create_project(client, str(workspace_root))
    set_node_phase(client, project_one, node_one, "executing")
    set_node_phase(client, project_two, node_two, "executing")

    first = client.post(
        f"/v2/projects/{project_one}/nodes/{node_one}/conversations/execution/send",
        json={"content": "hello one"},
    )
    second = client.post(
        f"/v2/projects/{project_two}/nodes/{node_two}/conversations/execution/send",
        json={"content": "hello two"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    wait_for_conversation(client, project_one, node_one, lambda item: item["record"]["status"] == "completed")
    wait_for_conversation(client, project_two, node_two, lambda item: item["record"]["status"] == "completed")
    assert len(factory.created) == 2
    assert factory.created[0][1] is not factory.created[1][1]


def test_execution_events_reject_stale_expected_stream_id(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")
    conversation = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution").json()["conversation"]
    conversation_id = conversation["record"]["conversation_id"]
    session = client.app.state.codex_session_manager.get_or_create_session(project_id, str(workspace_root))
    with session.lock:
        session.active_streams[conversation_id] = "stream_live"
        session.active_turns[conversation_id] = "turn_live"

    response = client.get(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/events",
        params={"expected_stream_id": "stream_old"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conversation_stream_mismatch"


def test_execution_send_rejects_concurrent_turns(client: TestClient, workspace_root) -> None:
    release = threading.Event()
    fake_client = FakeConversationClient(block_event=release, final_text="")
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))
    set_node_phase(client, project_id, node_id, "executing")

    first = client.post(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
        json={"content": "hello"},
    )

    assert first.status_code == 202
    assert fake_client.started.wait(timeout=1)

    second = client.post(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
        json={"content": "again"},
    )

    assert second.status_code == 409
    assert second.json()["code"] == "chat_turn_already_active"

    release.set()
    wait_for_conversation(
        client,
        project_id,
        node_id,
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )


def test_execution_send_rejects_non_executing_node_before_mutation(client: TestClient, workspace_root) -> None:
    fake_client = FakeConversationClient(final_text="hello")
    attach_session_client_factory(client, lambda _workspace_root: fake_client)
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send",
        json={"content": "hello"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "node_update_not_allowed"
    assert client.app.state.codex_session_manager.get_session(project_id) is None


def test_app_shutdown_flushes_gateway_before_session_manager_shutdown(monkeypatch, data_root) -> None:
    call_order: list[str] = []

    def record_gateway_flush(self) -> None:
        call_order.append("gateway_flush")

    def record_session_shutdown(self) -> None:
        call_order.append("session_shutdown")

    monkeypatch.setattr(backend_main.ConversationGateway, "flush_and_stop", record_gateway_flush)
    monkeypatch.setattr(backend_main.CodexSessionManager, "shutdown", record_session_shutdown)

    app = backend_main.create_app(data_root=data_root)
    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200

    assert call_order[:2] == ["gateway_flush", "session_shutdown"]
