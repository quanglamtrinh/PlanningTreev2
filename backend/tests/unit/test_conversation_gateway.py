from __future__ import annotations

import asyncio
import threading
import time

import pytest

from backend.ai.codex_client import RuntimeRequestRecord
from backend.conversation.contracts import make_conversation_message, make_conversation_part
from backend.errors.app_errors import ConversationPersistenceUnavailable
from backend.services.codex_session_manager import CodexSessionManager
from backend.services.conversation_context_builder import ConversationContextBuilder
from backend.services.conversation_gateway import ConversationGateway, _LiveConversationState
from backend.services.project_service import ProjectService
from backend.services.thread_service import PLANNING_STALE_TURN_ERROR, ThreadService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.conversation_broker import ConversationEventBroker


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


class StubAskService:
    def __init__(self, session_state: dict[str, object]) -> None:
        self._session_state = session_state

    def get_session_state(self, project_id: str, node_id: str) -> dict[str, object]:
        assert self._session_state["project_id"] == project_id
        assert self._session_state["node_id"] == node_id
        return self._session_state

    def create_message(self, project_id: str, node_id: str, content: object) -> dict[str, object]:
        raise NotImplementedError


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
    ask_service=None,
) -> tuple[ConversationGateway, ConversationEventBroker, CodexSessionManager]:
    session_manager = CodexSessionManager(client_factory=lambda _workspace_root: fake_client)
    broker = ConversationEventBroker()
    gateway = ConversationGateway(
        storage,
        tree_service,
        ThreadService(storage, tree_service, fake_client),
        session_manager,
        broker,
        ConversationContextBuilder(storage),
        ask_service,
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


def test_get_ask_conversation_normalizes_legacy_ask_state_into_v2_snapshot(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    ask_service = StubAskService(
        {
            "project_id": project_id,
            "node_id": node_id,
            "conversation_id": "convask_1",
            "thread_id": "ask_1",
            "forked_from_planning_thread_id": "planning_1",
            "created_at": "2026-03-15T00:00:00Z",
            "active_turn_id": None,
            "event_seq": 4,
            "status": "idle",
            "delta_context_packets": [],
            "messages": [
                {
                    "message_id": "msg_user_1",
                    "role": "user",
                    "turn_id": "turn_1",
                    "content": "What changed?",
                    "status": "completed",
                    "created_at": "2026-03-15T00:00:01Z",
                    "updated_at": "2026-03-15T00:00:01Z",
                    "error": None,
                },
                {
                    "message_id": "msg_assistant_1",
                    "role": "assistant",
                    "turn_id": "turn_1",
                    "content": "We tightened the ask host.",
                    "status": "completed",
                    "created_at": "2026-03-15T00:00:02Z",
                    "updated_at": "2026-03-15T00:00:03Z",
                    "error": None,
                },
            ],
        }
    )
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient(), ask_service=ask_service)

    conversation = gateway.get_ask_conversation(project_id, node_id)

    assert conversation["record"]["conversation_id"] == "convask_1"
    assert conversation["record"]["thread_type"] == "ask"
    assert conversation["record"]["current_runtime_mode"] == "ask"
    assert conversation["record"]["status"] == "completed"
    assert conversation["record"]["active_stream_id"] is None
    assert conversation["record"]["event_seq"] == 12
    assert conversation["record"]["app_server_thread_id"] == "ask_1"
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert conversation["messages"][1]["parts"][0]["part_type"] == "assistant_text"
    assert conversation["messages"][1]["parts"][0]["payload"]["text"] == "We tightened the ask host."

    gateway.flush_and_stop()


def test_translate_ask_event_expands_legacy_ask_events_into_normalized_conversation_events(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())

    created_events = gateway.translate_ask_event(
        {
            "type": "ask_message_created",
            "event_seq": 1,
            "conversation_id": "convask_1",
            "turn_id": "turn_1",
            "stream_id": "ask_stream:turn_1",
            "active_turn_id": "turn_1",
            "user_message": {
                "message_id": "msg_user_1",
                "role": "user",
                "turn_id": "turn_1",
                "content": "hello",
                "status": "completed",
                "created_at": "2026-03-15T00:00:01Z",
                "updated_at": "2026-03-15T00:00:01Z",
                "error": None,
            },
            "assistant_message": {
                "message_id": "msg_assistant_1",
                "role": "assistant",
                "turn_id": "turn_1",
                "content": "",
                "status": "pending",
                "created_at": "2026-03-15T00:00:01Z",
                "updated_at": "2026-03-15T00:00:01Z",
                "error": None,
            },
        }
    )
    completed_events = gateway.translate_ask_event(
        {
            "type": "ask_assistant_completed",
            "event_seq": 3,
            "conversation_id": "convask_1",
            "turn_id": "turn_1",
            "stream_id": "ask_stream:turn_1",
            "message_id": "msg_assistant_1",
            "content": "hello world",
            "updated_at": "2026-03-15T00:00:03Z",
        }
    )

    assert [event["event_type"] for event in created_events] == ["message_created", "message_created"]
    assert [event["event_seq"] for event in created_events] == [1, 2]
    assert created_events[0]["payload"]["message"]["role"] == "user"
    assert created_events[1]["payload"]["message"]["role"] == "assistant"
    assert [event["event_type"] for event in completed_events] == ["assistant_text_final", "completion_status"]
    assert [event["event_seq"] for event in completed_events] == [8, 9]
    assert completed_events[0]["payload"]["text"] == "hello world"
    assert completed_events[1]["payload"]["status"] == "completed"

    gateway.flush_and_stop()


def test_get_planning_conversation_normalizes_planning_history_into_v2_snapshot(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    storage.thread_store.replace_planning_turns(
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
            {
                "turn_id": "turn_merge_1",
                "role": "context_merge",
                "summary": "Preserve dependency constraint",
                "content": "Keep the shared dependency stable before splitting.",
                "packet_id": "packet_1",
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:04Z",
            },
        ],
    )
    storage.thread_store.set_planning_status(
        project_id,
        node_id,
        thread_id="planning_thread_1",
        status="idle",
        active_turn_id=None,
    )
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())

    conversation = gateway.get_planning_conversation(project_id, node_id)

    assert conversation["record"]["thread_type"] == "planning"
    assert conversation["record"]["current_runtime_mode"] == "planning"
    assert conversation["record"]["conversation_id"]
    assert conversation["record"]["app_server_thread_id"] == "planning_thread_1"
    assert conversation["record"]["status"] == "completed"
    assert conversation["record"]["event_seq"] == 12
    assert [message["role"] for message in conversation["messages"]] == [
        "user",
        "assistant",
        "assistant",
    ]
    split_message = conversation["messages"][1]
    assert split_message["parts"][0]["payload"]["text"] == "Split completed. Created 2 child tasks."
    assert split_message["parts"][1]["part_type"] == "tool_call"
    assert split_message["parts"][1]["payload"]["tool_name"] == "emit_render_data"
    assert conversation["messages"][2]["parts"][0]["payload"]["text"] == (
        "Preserve dependency constraint\n\nKeep the shared dependency stable before splitting."
    )

    gateway.flush_and_stop()


def test_get_planning_conversation_surfaces_recovered_stale_turn_as_terminal_visible_error(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    storage.thread_store.replace_planning_turns(
        project_id,
        node_id,
        [
            {
                "turn_id": "turn_stale_1",
                "role": "user",
                "content": "Split this node.",
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:01Z",
            },
            {
                "turn_id": "turn_stale_1",
                "role": "assistant",
                "content": PLANNING_STALE_TURN_ERROR,
                "is_inherited": False,
                "origin_node_id": node_id,
                "timestamp": "2026-03-15T00:00:02Z",
            },
        ],
    )
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())

    conversation = gateway.get_planning_conversation(project_id, node_id)

    assert conversation["record"]["status"] == "error"
    assert conversation["messages"][-1]["status"] == "error"
    assert conversation["messages"][-1]["error"] == PLANNING_STALE_TURN_ERROR
    assert conversation["messages"][-1]["parts"][0]["payload"]["text"] == PLANNING_STALE_TURN_ERROR

    gateway.flush_and_stop()


def test_translate_planning_event_expands_legacy_planning_events_into_normalized_conversation_events(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    gateway, _, _ = build_gateway(storage, tree_service, FakeConversationClient())

    started_events = gateway.translate_planning_event(
        {
            "type": "planning_turn_started",
            "conversation_id": "convplan_1",
            "turn_id": "turn_1",
            "stream_id": "planning_stream:turn_1",
            "user_content": "Split this node into slices.",
            "user_event_seq": 1,
            "assistant_event_seq": 2,
            "timestamp": "2026-03-15T00:00:01Z",
        }
    )
    completed_events = gateway.translate_planning_event(
        {
            "type": "planning_turn_completed",
            "conversation_id": "convplan_1",
            "turn_id": "turn_1",
            "stream_id": "planning_stream:turn_1",
            "assistant_text": "Split completed. Created 2 child tasks.",
            "assistant_text_event_seq": 3,
            "completion_event_seq": 4,
            "timestamp": "2026-03-15T00:00:03Z",
        }
    )
    failed_events = gateway.translate_planning_event(
        {
            "type": "planning_turn_failed",
            "conversation_id": "convplan_1",
            "turn_id": "turn_2",
            "stream_id": "planning_stream:turn_2",
            "assistant_text": "Split failed: planner crashed",
            "assistant_text_event_seq": 5,
            "completion_event_seq": 6,
            "timestamp": "2026-03-15T00:00:05Z",
        }
    )

    assert [event["event_type"] for event in started_events] == ["message_created", "message_created"]
    assert started_events[0]["payload"]["message"]["role"] == "user"
    assert started_events[1]["payload"]["message"]["role"] == "assistant"
    assert started_events[1]["payload"]["message"]["status"] == "pending"

    assert [event["event_type"] for event in completed_events] == [
        "assistant_text_final",
        "completion_status",
    ]
    assert completed_events[0]["payload"]["text"] == "Split completed. Created 2 child tasks."
    assert completed_events[1]["payload"]["status"] == "completed"

    assert [event["event_type"] for event in failed_events] == [
        "assistant_text_final",
        "completion_status",
    ]
    assert failed_events[0]["payload"]["status"] == "error"
    assert failed_events[1]["payload"]["status"] == "error"
    assert failed_events[1]["payload"]["error"] == "Split failed: planner crashed"

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


def test_success_path_emits_and_persists_execution_tool_calls(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
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
    gateway, broker, _ = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    response, events = asyncio.run(
        collect_gateway_events(
            broker,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: gateway.send_execution_message(project_id, node_id, "render the split"),
            terminal_statuses={"completed"},
        )
    )
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed",
    )
    assistant_message = snapshot["messages"][-1]

    assert [event["event_type"] for event in events] == [
        "message_created",
        "message_created",
        "tool_call_start",
        "assistant_text_final",
        "completion_status",
    ]
    assert [int(event["event_seq"]) for event in events] == [1, 2, 3, 4, 5]
    assert events[2]["message_id"] == response["assistant_message_id"]
    assert events[2]["item_id"] == f"{response['assistant_message_id']}:tool_call:0"
    assert events[2]["payload"]["tool_name"] == "emit_render_data"
    assert len(assistant_message["parts"]) == 2
    assert assistant_message["parts"][1]["part_type"] == "tool_call"
    assert assistant_message["parts"][1]["part_id"] == f"{response['assistant_message_id']}:tool_call:0"
    assert assistant_message["parts"][1]["payload"]["tool_call_id"] == assistant_message["parts"][1]["part_id"]
    assert assistant_message["parts"][1]["payload"]["tool_name"] == "emit_render_data"
    assert assistant_message["parts"][1]["payload"]["arguments"]["kind"] == "split_result"

    gateway.flush_and_stop()


def test_success_path_emits_and_reconciles_execution_plan_blocks_without_duplicate_parts(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
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
    gateway, broker, _ = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    response, events = asyncio.run(
        collect_gateway_events(
            broker,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: gateway.send_execution_message(project_id, node_id, "plan this"),
            terminal_statuses={"completed"},
        )
    )
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed",
    )
    assistant_message = snapshot["messages"][-1]
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
    assert [int(event["event_seq"]) for event in events] == [1, 2, 3, 4, 5, 6, 7]
    assert len(plan_events) == 3
    assert {event["item_id"] for event in plan_events} == {
        f"{response['assistant_message_id']}:plan_block:plan_1"
    }
    assert [part["part_type"] for part in assistant_message["parts"]] == ["assistant_text", "plan_block"]
    assert assistant_message["parts"][1]["part_id"] == f"{response['assistant_message_id']}:plan_block:plan_1"
    assert assistant_message["parts"][1]["item_key"] == "plan_1"
    assert assistant_message["parts"][1]["payload"]["text"] == "Final plan"

    gateway.flush_and_stop()


def test_success_path_emits_and_persists_execution_user_input_requests(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(
        runtime_requests=[
            {
                "request_id": "req_exec_1",
                "turn_id": "turn_1",
                "item_id": "item_req_1",
                "title": "Need input",
                "summary": "One short answer is needed.",
                "prompt": "Answer from the host surface.",
                "questions": [
                    {
                        "id": "brand_direction",
                        "header": "Brand direction",
                        "question": "What visual direction should we use?",
                        "options": [
                            {"label": "Editorial", "description": "Structured and dense."},
                            {"label": "Playful", "description": "Expressive and bold."},
                        ],
                    }
                ],
            }
        ],
        final_text="Waiting no longer.",
    )
    gateway, broker, _ = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    response, events = asyncio.run(
        collect_gateway_events(
            broker,
            project_id=project_id,
            conversation_id=conversation_id,
            action=lambda: gateway.send_execution_message(project_id, node_id, "continue"),
            terminal_statuses={"completed"},
        )
    )
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed",
    )

    request_events = [event for event in events if event["event_type"] == "request_user_input"]
    assert len(request_events) == 1
    assert request_events[0]["payload"]["message"]["message_id"] == "request_message:req_exec_1"
    assert request_events[0]["payload"]["message"]["parts"][0]["part_type"] == "user_input_request"
    assert request_events[0]["payload"]["message"]["parts"][0]["payload"]["request_id"] == "req_exec_1"
    assert [message["role"] for message in snapshot["messages"]] == ["user", "assistant", "assistant"]
    request_message = snapshot["messages"][1]
    assert request_message["message_id"] == "request_message:req_exec_1"
    assert request_message["parts"][0]["part_type"] == "user_input_request"
    assert request_message["parts"][0]["payload"]["resolution_state"] == "pending"

    gateway.flush_and_stop()


def test_resolve_execution_request_persists_response_and_emits_interactive_events(
    storage: Storage,
    tree_service: TreeService,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, tree_service, project_id, node_id, "executing")
    fake_client = FakeConversationClient(
        runtime_requests=[
            {
                "request_id": "req_exec_2",
                "turn_id": "turn_1",
                "item_id": "item_req_2",
                "wait_for_resolution": True,
                "questions": [
                    {
                        "id": "brand_direction",
                        "header": "Brand direction",
                        "question": "What visual direction should we use?",
                        "options": [],
                    }
                ],
            }
        ],
        final_text="Continuing after input.",
    )
    gateway, broker, _ = build_gateway(storage, tree_service, fake_client)
    conversation_id = gateway.get_execution_conversation(project_id, node_id)["record"]["conversation_id"]

    async def run() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
        queue = broker.subscribe(project_id, conversation_id)
        try:
            response = gateway.send_execution_message(project_id, node_id, "continue")
            events: list[dict[str, object]] = []
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=1)
                events.append(event)
                if event["event_type"] == "request_user_input":
                    break

            resolution = gateway.resolve_execution_request(
                project_id,
                node_id,
                "req_exec_2",
                request_kind="user_input",
                decision=None,
                answers={"brand_direction": {"answers": ["Editorial"]}},
                thread_id="thread_exec_1",
                turn_id="turn_1",
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
            return response, resolution, events
        finally:
            broker.unsubscribe(project_id, conversation_id, queue)

    response, resolution, events = asyncio.run(run())
    snapshot = wait_for_snapshot(
        storage,
        project_id,
        str(response["conversation_id"]),
        lambda item: item["record"]["status"] == "completed",
    )

    assert resolution == {"status": "resolved"}
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
    response_message = next(
        message for message in snapshot["messages"] if message["message_id"] == "request_response:req_exec_2"
    )
    assert response_message["role"] == "user"
    assert response_message["parts"][0]["part_type"] == "user_input_response"
    assert response_message["parts"][0]["payload"]["answers"] == {
        "brand_direction": {"answers": ["Editorial"]}
    }
    request_message = next(message for message in snapshot["messages"] if message["message_id"] == "request_message:req_exec_2")
    assert request_message["parts"][0]["payload"]["resolution_state"] == "resolved"

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
