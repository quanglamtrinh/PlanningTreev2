from __future__ import annotations

import asyncio
import threading
import time

from backend.conversation.contracts import make_conversation_message, make_conversation_part
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
    assert snapshot["record"]["status"] == "active"
    assert snapshot["record"]["active_stream_id"] == response["stream_id"]
    assert snapshot["record"]["event_seq"] == 2
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
