from __future__ import annotations

import asyncio
import json
import threading
import time

from fastapi.testclient import TestClient

import backend.main as backend_main
from backend.routes.conversation import stream_execution_conversation_events
from backend.services.conversation_gateway import _LiveConversationState
from backend.tests.integration.test_chat_api import FakeCodexClient, attach_fake_client


class FakeConversationClient:
    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        final_text: str | None = None,
        block_event: threading.Event | None = None,
        raise_error: Exception | None = None,
        returned_thread_id: str = "thread_exec_1",
    ) -> None:
        self.deltas = list(deltas or [])
        self.final_text = final_text
        self.block_event = block_event
        self.raise_error = raise_error
        self.returned_thread_id = returned_thread_id
        self.started = threading.Event()
        self.calls: list[dict[str, object]] = []

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
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
        if callable(on_delta):
            for delta in self.deltas:
                on_delta(delta)
        return {
            "stdout": self.final_text if self.final_text is not None else "".join(self.deltas),
            "thread_id": self.returned_thread_id,
        }

    def stop(self) -> None:
        return None


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
