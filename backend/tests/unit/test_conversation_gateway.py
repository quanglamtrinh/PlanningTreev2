from __future__ import annotations

import asyncio
import threading
import time

import pytest

from backend.conversation.contracts import make_conversation_message, make_conversation_part
from backend.errors.app_errors import ConversationPersistenceUnavailable
from backend.services.codex_session_manager import CodexSessionManager
from backend.services.conversation_context_builder import ConversationContextBuilder
from backend.services.conversation_gateway import ConversationGateway, _LiveConversationState
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.conversation_broker import ConversationEventBroker


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


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def set_node_phase(storage: Storage, tree_service: TreeService, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    tree_service.node_index(snapshot)[node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def build_gateway(
    storage: Storage,
    tree_service: TreeService,
    fake_client: FakeConversationClient,
) -> tuple[ConversationGateway, ConversationEventBroker, CodexSessionManager]:
    session_manager = CodexSessionManager(client_factory=lambda _workspace_root: fake_client)
    broker = ConversationEventBroker()
    gateway = ConversationGateway(
        storage,
        tree_service,
        session_manager,
        broker,
        ConversationContextBuilder(storage),
    )
    return gateway, broker, session_manager


def wait_for_snapshot(
    storage: Storage,
    project_id: str,
    conversation_id: str,
    predicate,
    timeout: float = 2.0,
):
    deadline = time.time() + timeout
    last_snapshot = None
    while time.time() < deadline:
        last_snapshot = storage.conversation_store.get_conversation(project_id, conversation_id)
        if last_snapshot is not None and predicate(last_snapshot):
            return last_snapshot
        time.sleep(0.02)
    raise AssertionError(f"conversation did not reach the expected state: {last_snapshot}")


async def collect_gateway_events(
    broker: ConversationEventBroker,
    *,
    project_id: str,
    conversation_id: str,
    action,
    terminal_statuses: set[str],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    queue = broker.subscribe(project_id, conversation_id)
    try:
        response = action()
        events: list[dict[str, object]] = []
        deadline = time.time() + 3
        while time.time() < deadline:
            event = await asyncio.wait_for(queue.get(), timeout=max(0.01, deadline - time.time()))
            events.append(event)
            if event.get("event_type") == "completion_status":
                status = str(event.get("payload", {}).get("status") or "")
                if status in terminal_statuses:
                    break
        return response, events
    finally:
        broker.unsubscribe(project_id, conversation_id, queue)


def block_completion_persistence(gateway: ConversationGateway, monkeypatch) -> tuple[threading.Event, threading.Event]:
    completion_started = threading.Event()
    release_completion = threading.Event()
    original_build = gateway._build_completion_persistence_task

    def wrapped_build(*args, **kwargs):
        task = original_build(*args, **kwargs)
        original_run = task.run

        def run() -> None:
            completion_started.set()
            release_completion.wait()
            original_run()

        task.run = run
        return task

    monkeypatch.setattr(gateway, "_build_completion_persistence_task", wrapped_build)
    return completion_started, release_completion


def block_send_start_persistence(gateway: ConversationGateway, monkeypatch) -> tuple[threading.Event, threading.Event]:
    send_start_started = threading.Event()
    release_send_start = threading.Event()
    original_build = gateway._build_send_start_persistence_task

    def wrapped_build(*args, **kwargs):
        task = original_build(*args, **kwargs)
        original_run = task.run

        def run() -> None:
            send_start_started.set()
            release_send_start.wait()
            original_run()

        task.run = run
        return task

    monkeypatch.setattr(gateway, "_build_send_start_persistence_task", wrapped_build)
    return send_start_started, release_send_start


def test_get_execution_conversation_creates_one_canonical_snapshot_per_scope(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())

    first = gateway.get_execution_conversation(project_id, node_id)
    second = gateway.get_execution_conversation(project_id, node_id)

    assert first["record"]["conversation_id"] == second["record"]["conversation_id"]
    assert first["record"]["event_seq"] == 0
    assert first["record"]["active_stream_id"] is None
    assert first["messages"] == []

    gateway.flush_and_stop()


def test_send_execution_message_seeds_stable_messages_and_explicit_message_created_sequences(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    release = threading.Event()
    gateway, broker, _ = build_gateway(
        storage,
        tree_service,
        FakeConversationClient(block_event=release, final_text=""),
    )
    send_start_started, release_send_start = block_send_start_persistence(gateway, monkeypatch)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    async def run() -> tuple[dict[str, object], list[dict[str, object]]]:
        queue = broker.subscribe(project_id, conversation_id)
        try:
            response = gateway.send_execution_message(project_id, node_id, "hello")
            events = [
                await asyncio.wait_for(queue.get(), timeout=1),
                await asyncio.wait_for(queue.get(), timeout=1),
            ]
            return response, events
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

    response, events = asyncio.run(run())
    snapshot = storage.conversation_store.get_conversation(project_id, conversation_id)

    assert response["conversation_id"] == conversation_id
    assert events[0]["event_type"] == "message_created"
    assert events[0]["event_seq"] == 1
    assert events[0]["payload"]["message"]["role"] == "user"
    assert events[1]["event_type"] == "message_created"
    assert events[1]["event_seq"] == 2
    assert events[1]["payload"]["message"]["role"] == "assistant"
    assert snapshot is not None
    assert send_start_started.wait(timeout=1)
    assert snapshot["record"]["status"] == "idle"
    assert snapshot["record"]["active_stream_id"] is None
    assert snapshot["record"]["event_seq"] == 0
    assert snapshot["messages"] == []

    release_send_start.set()
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        conversation_id,
        lambda item: item["record"]["status"] == "active" and item["record"]["active_stream_id"] == response["stream_id"],
    )
    assert len(snapshot["messages"]) == 2
    assert snapshot["messages"][1]["message_id"] == response["assistant_message_id"]
    assert snapshot["messages"][1]["parts"][0]["part_id"] == response["assistant_text_part_id"]

    release.set()
    wait_for_snapshot(
        storage,
        project_id,
        conversation_id,
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )
    gateway.flush_and_stop()


def test_assistant_deltas_and_final_text_target_same_placeholder_and_persist_event_seq(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(deltas=["hello ", "world"], final_text="hello world")
    gateway, _, session_manager = build_gateway(storage, tree_service, fake_client)

    response = gateway.send_execution_message(project_id, node_id, "hello")
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )

    assistant_message = next(
        message for message in snapshot["messages"] if message["message_id"] == response["assistant_message_id"]
    )

    assert assistant_message["status"] == "completed"
    assert assistant_message["parts"][0]["part_id"] == response["assistant_text_part_id"]
    assert assistant_message["parts"][0]["payload"]["text"] == "hello world"
    assert snapshot["record"]["event_seq"] == 6
    assert snapshot["record"]["app_server_thread_id"] == "thread_exec_1"
    session = session_manager.get_session(project_id)
    assert session is not None
    with session.lock:
        assert session.active_streams == {}
        assert session.active_turns == {}
        assert session.loaded_runtime_threads["thread_exec_1"].status == "idle"

    gateway.flush_and_stop()


def test_send_start_persistence_is_enqueued_before_delta_and_completion_tasks(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(deltas=["hello"], final_text="hello")
    gateway, _, _ = build_gateway(storage, tree_service, fake_client)

    def tag_builder(kind: str, original):
        def wrapped(*args, **kwargs):
            task = original(*args, **kwargs)
            setattr(task, "_kind", kind)
            return task

        return wrapped

    monkeypatch.setattr(
        gateway,
        "_build_send_start_persistence_task",
        tag_builder("send_start", gateway._build_send_start_persistence_task),
    )
    monkeypatch.setattr(
        gateway,
        "_build_delta_persistence_task",
        tag_builder("delta", gateway._build_delta_persistence_task),
    )
    monkeypatch.setattr(
        gateway,
        "_build_final_text_persistence_task",
        tag_builder("final_text", gateway._build_final_text_persistence_task),
    )
    monkeypatch.setattr(
        gateway,
        "_build_completion_persistence_task",
        tag_builder("completion", gateway._build_completion_persistence_task),
    )

    enqueued: list[str] = []
    original_enqueue = gateway._enqueue_persistence_task

    def wrapped_enqueue(task) -> None:
        enqueued.append(str(getattr(task, "_kind", "unknown")))
        original_enqueue(task)

    monkeypatch.setattr(gateway, "_enqueue_persistence_task", wrapped_enqueue)

    response = gateway.send_execution_message(project_id, node_id, "hello")
    wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )

    assert enqueued[0] == "send_start"
    assert "delta" in enqueued[1:]
    assert "completion" in enqueued[1:]
    gateway.flush_and_stop()


def test_success_path_emits_strictly_monotonic_events_with_stable_assistant_target(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(deltas=["hello ", "world"], final_text="hello world")
    gateway, broker, _ = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    response, events = asyncio.run(
        collect_gateway_events(
            broker,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: gateway.send_execution_message(project_id, node_id, "hello"),
            terminal_statuses={"completed"},
        )
    )

    event_types = [event["event_type"] for event in events]
    event_seqs = [int(event["event_seq"]) for event in events]
    assistant_text_events = [
        event for event in events if event["event_type"] in {"assistant_text_delta", "assistant_text_final"}
    ]

    assert event_types == [
        "message_created",
        "message_created",
        "assistant_text_delta",
        "assistant_text_delta",
        "assistant_text_final",
        "completion_status",
    ]
    assert event_seqs == [1, 2, 3, 4, 5, 6]
    assert event_seqs == sorted(event_seqs)
    assert len(set(event_seqs)) == len(event_seqs)
    assert {event["conversation_id"] for event in events} == {str(response["conversation_id"])}
    assert {event["stream_id"] for event in events} == {str(response["stream_id"])}
    assert events[0]["message_id"] == response["user_message_id"]
    assert events[1]["message_id"] == response["assistant_message_id"]
    assert events[-1]["message_id"] == response["assistant_message_id"]
    assert {event["message_id"] for event in assistant_text_events} == {str(response["assistant_message_id"])}
    assert {event["item_id"] for event in assistant_text_events} == {str(response["assistant_text_part_id"])}

    gateway.flush_and_stop()


def test_send_execution_message_fails_before_publish_when_persistence_handoff_is_unavailable(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    gateway, broker, session_manager = build_gateway(storage, tree_service, FakeConversationClient())
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]
    gateway.flush_and_stop()

    async def run() -> None:
        queue = broker.subscribe(project_id, conversation_id)
        try:
            with pytest.raises(ConversationPersistenceUnavailable):
                gateway.send_execution_message(project_id, node_id, "hello")
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=0.05)
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

    asyncio.run(run())
    snapshot = storage.conversation_store.get_conversation(project_id, conversation_id)
    assert snapshot is not None
    assert snapshot["record"]["status"] == "idle"
    assert snapshot["record"]["active_stream_id"] is None
    assert snapshot["messages"] == []
    session = session_manager.get_session(project_id)
    assert session is not None
    with session.lock:
        assert session.active_streams == {}
        assert session.active_turns == {}


def test_send_execution_message_repairs_interrupted_state_when_send_start_enqueue_fails_after_publish(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(block_event=threading.Event(), final_text="")
    gateway, broker, session_manager = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    call_count = 0

    def fail_first_enqueue(task) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("send-start enqueue failed")
        gateway._persistence_queue.put(task)

    monkeypatch.setattr(gateway, "_enqueue_persistence_task", fail_first_enqueue)

    async def run() -> list[dict[str, object]]:
        queue = broker.subscribe(project_id, conversation_id)
        try:
            with pytest.raises(ConversationPersistenceUnavailable):
                gateway.send_execution_message(project_id, node_id, "hello")
            return [
                await asyncio.wait_for(queue.get(), timeout=1),
                await asyncio.wait_for(queue.get(), timeout=1),
            ]
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

    events = asyncio.run(run())
    snapshot = storage.conversation_store.get_conversation(project_id, conversation_id)

    assert [event["event_type"] for event in events] == ["message_created", "message_created"]
    assert fake_client.started.is_set() is False
    assert snapshot is not None
    assert snapshot["record"]["status"] == "interrupted"
    assert snapshot["record"]["active_stream_id"] is None
    assert snapshot["record"]["event_seq"] == 2
    assert len(snapshot["messages"]) == 2
    assert snapshot["messages"][1]["status"] == "interrupted"
    assert snapshot["messages"][1]["parts"][0]["status"] == "interrupted"
    assert snapshot["messages"][1]["error"] == "Execution conversation was interrupted before completion."
    session = session_manager.get_session(project_id)
    assert session is not None
    with session.lock:
        assert session.active_streams == {}
        assert session.active_turns == {}
    gateway.flush_and_stop()


def test_stale_stream_callbacks_are_ignored_after_owner_changes(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    release = threading.Event()
    gateway, _, session_manager = build_gateway(
        storage,
        tree_service,
        FakeConversationClient(block_event=release, final_text=""),
    )

    response = gateway.send_execution_message(project_id, node_id, "hello")
    conversation_id = str(response["conversation_id"])
    session = session_manager.get_session(project_id)
    assert session is not None
    with session.lock:
        session.active_streams[conversation_id] = "stream_new"
        session.active_turns[conversation_id] = "turn_new"

    gateway._handle_assistant_delta(
        project_id=project_id,
        conversation_id=conversation_id,
        stream_id=str(response["stream_id"]),
        turn_id=str(response["turn_id"]),
        assistant_message_id=str(response["assistant_message_id"]),
        assistant_part_id=str(response["assistant_text_part_id"]),
        delta="ignored",
    )
    gateway.flush_persistence()
    snapshot = storage.conversation_store.get_conversation(project_id, conversation_id)

    assert snapshot is not None
    assert snapshot["record"]["event_seq"] == 2
    assert snapshot["messages"][1]["parts"][0]["payload"]["text"] == ""

    release.set()
    with session.lock:
        session.active_streams.pop(conversation_id, None)
        session.active_turns.pop(conversation_id, None)
    gateway.flush_and_stop()


def test_terminal_failure_after_setup_seed_emits_error_status_and_clears_ownership(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(raise_error=RuntimeError("boom"))
    gateway, broker, session_manager = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    async def run() -> tuple[dict[str, object], list[dict[str, object]]]:
        queue = broker.subscribe(project_id, conversation_id)
        try:
            response = gateway.send_execution_message(project_id, node_id, "hello")
            events = [
                await asyncio.wait_for(queue.get(), timeout=1),
                await asyncio.wait_for(queue.get(), timeout=1),
                await asyncio.wait_for(queue.get(), timeout=1),
            ]
            return response, events
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

    response, events = asyncio.run(run())
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "error" and item["record"]["active_stream_id"] is None,
    )

    assert [event["event_type"] for event in events] == [
        "message_created",
        "message_created",
        "completion_status",
    ]
    assert events[-1]["payload"]["status"] == "error"
    assert "boom" in str(events[-1]["payload"]["error"])
    assert snapshot["messages"][1]["status"] == "error"
    assert "boom" in str(snapshot["messages"][1]["error"])
    assert snapshot["record"]["event_seq"] == 3
    session = session_manager.get_session(project_id)
    assert session is not None
    with session.lock:
        assert session.active_streams == {}
        assert session.active_turns == {}

    gateway.flush_and_stop()


def test_terminal_success_keeps_ownership_until_completion_persistence_finishes(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    gateway, _, session_manager = build_gateway(
        storage,
        tree_service,
        FakeConversationClient(final_text="hello world"),
    )
    completion_started, release_completion = block_completion_persistence(gateway, monkeypatch)

    response = gateway.send_execution_message(project_id, node_id, "hello")
    conversation_id = str(response["conversation_id"])
    session = session_manager.get_session(project_id)

    assert session is not None
    assert completion_started.wait(timeout=1)

    with session.lock:
        assert session.active_streams[conversation_id] == response["stream_id"]
        assert session.active_turns[conversation_id] == response["turn_id"]

    in_flight = storage.conversation_store.get_conversation(project_id, conversation_id)
    assert in_flight is not None
    assert in_flight["record"]["status"] == "active"
    assert in_flight["record"]["active_stream_id"] == response["stream_id"]
    assert in_flight["record"]["app_server_thread_id"] is None

    release_completion.set()
    final_snapshot = wait_for_snapshot(
        storage,
        project_id,
        conversation_id,
        lambda item: (
            item["record"]["status"] == "completed"
            and item["record"]["active_stream_id"] is None
            and item["record"]["app_server_thread_id"] == "thread_exec_1"
        ),
    )

    assert final_snapshot["record"]["event_seq"] == 4
    with session.lock:
        assert session.active_streams == {}
        assert session.active_turns == {}

    gateway.flush_and_stop()


def test_flush_and_stop_waits_for_blocked_terminal_completion_persistence(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    gateway, _, _ = build_gateway(
        storage,
        tree_service,
        FakeConversationClient(final_text="hello world"),
    )
    completion_started, release_completion = block_completion_persistence(gateway, monkeypatch)

    response = gateway.send_execution_message(project_id, node_id, "hello")
    conversation_id = str(response["conversation_id"])

    assert completion_started.wait(timeout=1)

    flush_thread = threading.Thread(target=gateway.flush_and_stop, daemon=True)
    flush_thread.start()
    time.sleep(0.1)

    assert flush_thread.is_alive()

    release_completion.set()
    flush_thread.join(timeout=2)

    assert not flush_thread.is_alive()
    final_snapshot = wait_for_snapshot(
        storage,
        project_id,
        conversation_id,
        lambda item: item["record"]["status"] == "completed" and item["record"]["active_stream_id"] is None,
    )
    assert final_snapshot["record"]["app_server_thread_id"] == "thread_exec_1"


def test_get_snapshot_is_durable_store_first_and_only_enriches_live_metadata(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    gateway, _, session_manager = build_gateway(storage, tree_service, FakeConversationClient())
    snapshot = gateway.get_execution_conversation(project_id, node_id)
    conversation_id = snapshot["record"]["conversation_id"]

    assistant_message = make_conversation_message(
        conversation_id=conversation_id,
        turn_id="turn_1",
        role="assistant",
        runtime_mode="execute",
        status="streaming",
        parts=[
            make_conversation_part(
                part_type="assistant_text",
                order=0,
                status="streaming",
                payload={"text": "durable"},
            )
        ],
    )
    storage.conversation_store.upsert_message(project_id, conversation_id, assistant_message)

    session = session_manager.get_or_create_session(project_id, str(workspace_root))
    with session.lock:
        session.active_streams[conversation_id] = "stream_live"
        session.active_turns[conversation_id] = "turn_live"
        gateway._live_state[(project_id, conversation_id)] = _LiveConversationState(
            event_seq=7,
            assistant_text="memory only",
        )

    enriched = gateway.get_execution_conversation(project_id, node_id)

    assert enriched["record"]["active_stream_id"] == "stream_live"
    assert enriched["record"]["event_seq"] == 7
    assert enriched["messages"][0]["parts"][0]["payload"]["text"] == "durable"

    gateway.flush_and_stop()


def test_get_execution_conversation_repairs_orphaned_active_execution_snapshot_once(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())
    snapshot = gateway.get_execution_conversation(project_id, node_id)
    conversation_id = snapshot["record"]["conversation_id"]

    user_message = make_conversation_message(
        conversation_id=conversation_id,
        turn_id="turn_1",
        role="user",
        runtime_mode="execute",
        status="completed",
        parts=[make_conversation_part(part_type="user_text", order=0, status="completed", payload={"text": "hello"})],
    )
    assistant_message = make_conversation_message(
        conversation_id=conversation_id,
        turn_id="turn_1",
        role="assistant",
        runtime_mode="execute",
        status="pending",
        parts=[
            make_conversation_part(
                part_type="assistant_text",
                order=0,
                status="pending",
                payload={"text": ""},
            )
        ],
    )
    storage.conversation_store.upsert_message(project_id, conversation_id, user_message)
    storage.conversation_store.upsert_message(project_id, conversation_id, assistant_message)
    storage.conversation_store.mutate_conversation(
        project_id,
        conversation_id,
        lambda working_snapshot: working_snapshot["record"].update(
            {
                "status": "active",
                "active_stream_id": "stream_stale",
                "event_seq": 2,
            }
        ),
    )
    gateway._live_state[(project_id, conversation_id)] = _LiveConversationState(
        event_seq=3,
        assistant_text="stale text",
    )

    repaired = gateway.get_execution_conversation(project_id, node_id)
    repaired_again = gateway.get_execution_conversation(project_id, node_id)

    assert repaired["record"]["status"] == "interrupted"
    assert repaired["record"]["active_stream_id"] is None
    assert repaired["record"]["event_seq"] == 2
    assert repaired["messages"][1]["status"] == "interrupted"
    assert repaired["messages"][1]["parts"][0]["status"] == "interrupted"
    assert repaired["messages"][1]["error"] == "Execution conversation was interrupted before completion."
    assert (project_id, conversation_id) not in gateway._live_state
    assert repaired_again == repaired

    gateway.flush_and_stop()
