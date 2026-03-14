from __future__ import annotations

import copy
import threading
import time
from typing import Callable

import pytest

from backend.ai.ask_prompt_builder import ask_thread_render_tool
from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import (
    AskBlockedByPlanningActive,
    MergeBlockedBySplit,
    MergePlanningThreadUnavailable,
    InvalidPacketTransition,
    PacketMutationBlockedBySplit,
    PacketNotFound,
    AskThreadReadOnly,
    AskTurnAlreadyActive,
)
from backend.services.ask_service import STALE_ASK_TURN_ERROR, AskService
from backend.storage.storage import Storage


class CapturingAskEventBroker:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def publish(self, project_id: str, node_id: str, event: dict[str, object]) -> None:
        self.events.append(copy.deepcopy(event))


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
        self.resume_calls: list[dict[str, object]] = []
        self.fork_calls: list[dict[str, object]] = []
        self.run_turn_calls: list[dict[str, object]] = []
        self.tool_calls_to_emit: list[tuple[str, dict[str, object]]] = []
        self.on_run_turn: Callable[[], None] | None = None
        self._fork_counter = 0

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, object]:
        self.resume_calls.append(
            {
                "thread_id": thread_id,
                "cwd": cwd,
                "timeout_sec": timeout_sec,
                "writable_roots": writable_roots,
            }
        )
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
        self._fork_counter += 1
        thread_id = f"ask_{self._fork_counter}"
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
        self.run_turn_calls.append(
            {
                "prompt": prompt,
                "thread_id": thread_id,
                "timeout_sec": timeout_sec,
                "cwd": cwd,
                "writable_roots": writable_roots,
            }
        )
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        if callable(self.on_run_turn):
            self.on_run_turn()
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


class FakeThreadService:
    def __init__(self, storage: Storage, client: FakeCodexClient, *, planning_thread_id: str = "planning_1") -> None:
        self._storage = storage
        self._client = client
        self._planning_thread_id = planning_thread_id
        self.calls: list[tuple[str, str]] = []

    def ensure_planning_thread(self, project_id: str, node_id: str) -> str:
        self.calls.append((project_id, node_id))
        self._client.available_threads.add(self._planning_thread_id)
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node = snapshot["tree_state"]["node_index"].get(node_id)
            if node is not None:
                node["planning_thread_id"] = self._planning_thread_id
                self._storage.project_store.save_snapshot(project_id, snapshot)
                state = self._storage.node_store.load_state(project_id, node_id)
                state["planning_thread_id"] = self._planning_thread_id
                self._storage.node_store.save_state(project_id, node_id, state)
            self._storage.thread_store.set_planning_status(
                project_id,
                node_id,
                thread_id=self._planning_thread_id,
                status="idle",
                active_turn_id=None,
            )
        return self._planning_thread_id


def create_project(project_service, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_idle(storage: Storage, project_id: str, node_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = storage.thread_store.get_ask_state(project_id, node_id)
        if isinstance(session, dict) and session.get("active_turn_id") is None:
            return session
        time.sleep(0.02)
    raise AssertionError(f"ask session did not become idle for {node_id}")


def mark_node(storage: Storage, project_id: str, node_id: str, **updates: object) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    node = snapshot["tree_state"]["node_index"][node_id]
    node.update(updates)
    storage.project_store.save_snapshot(project_id, snapshot)
    if "title" in updates or "description" in updates:
        task = storage.node_store.load_task(project_id, node_id)
        if "title" in updates:
            task["title"] = str(updates["title"] or "")
        if "description" in updates:
            task["purpose"] = str(updates["description"] or "")
        storage.node_store.save_task(project_id, node_id, task)
    state_keys = {
        "phase",
        "planning_thread_id",
        "execution_thread_id",
        "planning_thread_forked_from_node",
        "planning_thread_bootstrapped_at",
        "chat_session_id",
    }
    if any(key in updates for key in state_keys):
        state = storage.node_store.load_state(project_id, node_id)
        for key in state_keys:
            if key in updates:
                state[key] = "" if updates[key] is None else updates[key]
        storage.node_store.save_state(project_id, node_id, state)


def write_invalid_task(storage: Storage, project_id: str, node_id: str) -> None:
    task_path = storage.node_store.node_dir(project_id, node_id) / "task.md"
    task_path.write_text("# Task\n\n## Title\nBroken\n\n## Title\nStill broken\n", encoding="utf-8")


def attach_active_child(storage: Storage, project_id: str, parent_id: str, child_id: str = "child_1") -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
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
    storage.project_store.save_snapshot(project_id, snapshot)
    storage.node_store.create_node_files(
        project_id,
        child_id,
        task={"title": "Child", "purpose": "", "responsibility": ""},
    )


def test_build_ask_prompt_uses_empty_task_fields_when_task_document_is_invalid(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    write_invalid_task(storage, project_id, root_id)
    client = FakeCodexClient()
    service = AskService(
        storage,
        client,
        CapturingAskEventBroker(),
        FakeThreadService(storage, client),
    )
    snapshot = storage.project_store.load_snapshot(project_id)
    node = snapshot["tree_state"]["node_index"][root_id]

    prompt = service._build_ask_prompt(
        project_id=project_id,
        snapshot=snapshot,
        node=node,
        workspace_root=str(workspace_root),
        user_message="hello",
    )

    assert '"node_title": ""' in prompt
    assert '"node_description": ""' in prompt


def make_service(storage: Storage, client: FakeCodexClient) -> tuple[AskService, CapturingAskEventBroker, FakeThreadService]:
    broker = CapturingAskEventBroker()
    thread_service = FakeThreadService(storage, client)
    service = AskService(storage, client, broker, thread_service)  # type: ignore[arg-type]
    return service, broker, thread_service


def test_get_session_returns_default_for_new_node(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())

    session = service.get_session(project_id, root_id)["session"]

    assert session["project_id"] == project_id
    assert session["node_id"] == root_id
    assert session["active_turn_id"] is None
    assert session["event_seq"] == 0
    assert session["status"] is None
    assert session["messages"] == []
    assert session["delta_context_packets"] == []
    assert "thread_id" not in session
    assert "config" not in session


def test_get_session_recovers_stale_active_turn(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.thread_store.write_ask_session(
        project_id,
        root_id,
        {
            "thread_id": "ask_1",
            "forked_from_planning_thread_id": "planning_1",
            "status": "active",
            "active_turn_id": "askturn_1",
            "messages": [
                {
                    "message_id": "msg_assistant",
                    "role": "assistant",
                    "content": "partial",
                    "status": "streaming",
                    "created_at": "2026-03-11T00:00:00Z",
                    "updated_at": "2026-03-11T00:00:01Z",
                    "error": None,
                }
            ],
            "event_seq": 7,
            "delta_context_packets": [],
            "created_at": "2026-03-11T00:00:00Z",
        },
    )
    service, _, _ = make_service(storage, FakeCodexClient())

    session = service.get_session(project_id, root_id)["session"]

    assert session["active_turn_id"] is None
    assert session["event_seq"] == 7
    assert session["messages"][0]["status"] == "error"
    assert session["messages"][0]["error"] == STALE_ASK_TURN_ERROR


def test_create_message_creates_user_and_assistant_messages(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    release = threading.Event()
    service, _, _ = make_service(storage, FakeCodexClient(block_event=release))

    response = service.create_message(project_id, root_id, "What are the risks?")

    assert response["status"] == "accepted"
    state = storage.thread_store.get_ask_state(project_id, root_id)
    assert state["thread_id"] == "ask_1"
    assert state["active_turn_id"] is not None
    assert len(state["messages"]) == 2
    assert state["messages"][0]["role"] == "user"
    assert state["messages"][1]["role"] == "assistant"

    release.set()
    wait_for_idle(storage, project_id, root_id)


def test_create_message_rejects_empty_content(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(ValueError, match="content is required"):
        service.create_message(project_id, root_id, "   ")


def test_create_message_rejects_when_ask_turn_active(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    client.available_threads.add("ask_existing")
    storage.thread_store.write_ask_session(
        project_id,
        root_id,
        {
            "thread_id": "ask_existing",
            "forked_from_planning_thread_id": "planning_1",
            "status": "active",
            "active_turn_id": "askturn_1",
            "messages": [],
            "event_seq": 2,
            "delta_context_packets": [],
            "created_at": "2026-03-11T00:00:00Z",
        },
    )
    service, _, _ = make_service(storage, client)

    with pytest.raises(AskTurnAlreadyActive):
        service.create_message(project_id, root_id, "again")


def test_create_message_rejects_done_node(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_node(storage, project_id, root_id, status="done")
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(AskThreadReadOnly):
        service.create_message(project_id, root_id, "hello")


def test_create_message_rejects_superseded_node(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_node(storage, project_id, root_id, is_superseded=True)
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(AskThreadReadOnly):
        service.create_message(project_id, root_id, "hello")


def test_create_message_rejects_when_planning_active(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        status="active",
        active_turn_id="planturn_1",
    )
    service, _, thread_service = make_service(storage, FakeCodexClient())

    with pytest.raises(AskBlockedByPlanningActive):
        service.create_message(project_id, root_id, "hello")

    assert thread_service.calls == []


def test_create_message_lazily_forks_ask_thread_from_planning_thread(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, thread_service = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    wait_for_idle(storage, project_id, root_id)

    assert thread_service.calls == [(project_id, root_id)]
    assert client.fork_calls[0]["source_thread_id"] == "planning_1"
    assert isinstance(client.fork_calls[0]["base_instructions"], str)
    assert client.fork_calls[0]["dynamic_tools"] == [ask_thread_render_tool()]


def test_existing_ask_thread_is_reused_when_available(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    client.available_threads.add("ask_existing")
    storage.thread_store.write_ask_session(
        project_id,
        root_id,
        {
            "thread_id": "ask_existing",
            "forked_from_planning_thread_id": "planning_1",
            "status": None,
            "active_turn_id": None,
            "messages": [],
            "event_seq": 0,
            "delta_context_packets": [],
            "created_at": "2026-03-11T00:00:00Z",
        },
    )
    service, _, thread_service = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    wait_for_idle(storage, project_id, root_id)

    assert client.resume_calls[0]["thread_id"] == "ask_existing"
    assert client.fork_calls == []
    assert thread_service.calls == []


def test_stale_ask_thread_is_recreated(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    storage.thread_store.write_ask_session(
        project_id,
        root_id,
        {
            "thread_id": "ask_stale",
            "forked_from_planning_thread_id": "planning_1",
            "status": None,
            "active_turn_id": None,
            "messages": [],
            "event_seq": 0,
            "delta_context_packets": [],
            "created_at": "2026-03-11T00:00:00Z",
        },
    )
    service, _, _ = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert client.resume_calls[0]["thread_id"] == "ask_stale"
    assert client.fork_calls
    assert session["thread_id"] == "ask_1"


def test_background_turn_completes_and_publishes_events(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, broker, _ = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert session["messages"][-1]["status"] == "completed"
    assert session["messages"][-1]["content"] == "hello world"
    assert [event["type"] for event in broker.events] == [
        "ask_message_created",
        "ask_assistant_delta",
        "ask_assistant_delta",
        "ask_assistant_completed",
    ]


def test_background_turn_failure_marks_error(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, broker, _ = make_service(storage, FakeCodexClient(raise_error=RuntimeError("boom")))

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert session["messages"][-1]["status"] == "error"
    assert "boom" in session["messages"][-1]["error"]
    assert broker.events[-1]["type"] == "ask_assistant_error"


def test_reset_session_clears_messages_and_thread_identity(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, broker, _ = make_service(storage, FakeCodexClient())

    service.create_message(project_id, root_id, "hello")
    completed = wait_for_idle(storage, project_id, root_id)
    reset = service.reset_session(project_id, root_id)["session"]
    stored = storage.thread_store.get_ask_state(project_id, root_id)

    assert completed["thread_id"] == "ask_1"
    assert reset["messages"] == []
    assert reset["status"] is None
    assert "thread_id" not in reset
    assert stored["thread_id"] is None
    assert stored["messages"] == []
    assert broker.events[-1]["type"] == "ask_session_reset"


def test_reset_session_preserves_delta_context_packets(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.thread_store.write_ask_session(
        project_id,
        root_id,
        {
            "thread_id": "ask_1",
            "forked_from_planning_thread_id": "planning_1",
            "status": "idle",
            "active_turn_id": None,
            "messages": [
                {
                    "message_id": "msg_1",
                    "role": "user",
                    "content": "hello",
                    "status": "completed",
                    "created_at": "2026-03-11T00:00:00Z",
                    "updated_at": "2026-03-11T00:00:00Z",
                    "error": None,
                }
            ],
            "event_seq": 4,
            "delta_context_packets": [
                {
                    "packet_id": "dctx_1",
                    "node_id": root_id,
                    "created_at": "2026-03-11T00:00:00Z",
                    "source_message_ids": [],
                    "summary": "s",
                    "context_text": "c",
                    "status": "pending",
                    "status_reason": None,
                    "merged_at": None,
                    "merged_planning_turn_id": None,
                    "suggested_by": "agent",
                }
            ],
            "created_at": "2026-03-11T00:00:00Z",
        },
    )
    service, _, _ = make_service(storage, FakeCodexClient())

    reset = service.reset_session(project_id, root_id)["session"]

    assert len(reset["delta_context_packets"]) == 1
    assert storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]["packet_id"] == "dctx_1"


def test_runtime_config_is_read_only_for_codex_calls(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, _ = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    wait_for_idle(storage, project_id, root_id)
    snapshot = storage.project_store.load_snapshot(project_id)
    project_workspace_root = snapshot["project"]["project_workspace_root"]

    assert client.run_turn_calls[0]["cwd"] == project_workspace_root
    assert client.run_turn_calls[0]["writable_roots"] == []


def test_tool_call_creates_delta_context_packet(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    client.tool_calls_to_emit = [
        (
            "emit_render_data",
            {
                "kind": "delta_context_suggestion",
                "payload": {
                    "summary": "API dependency",
                    "context_text": "Need stable upstream API contract before split.",
                },
            },
        )
    ]
    service, broker, _ = make_service(storage, client)

    response = service.create_message(project_id, root_id, "What blocks this?")
    session = wait_for_idle(storage, project_id, root_id)

    packet = session["delta_context_packets"][0]
    assert response["status"] == "accepted"
    assert packet["summary"] == "API dependency"
    assert packet["context_text"] == "Need stable upstream API contract before split."
    assert packet["status"] == "pending"
    assert packet["suggested_by"] == "agent"
    assert packet["source_message_ids"] == [response["user_message_id"], response["assistant_message_id"]]
    assert any(event["type"] == "ask_delta_context_suggested" for event in broker.events)


def test_tool_call_ignores_unknown_kind(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    client.tool_calls_to_emit = [("emit_render_data", {"kind": "unknown", "payload": {}})]
    service, _, _ = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert session["delta_context_packets"] == []


def test_tool_call_ignored_after_split(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    attach_active_child(storage, project_id, root_id)
    client = FakeCodexClient()
    client.tool_calls_to_emit = [
        (
            "emit_render_data",
            {
                "kind": "delta_context_suggestion",
                "payload": {
                    "summary": "Risk",
                    "context_text": "This should not persist after split.",
                },
            },
        )
    ]
    service, broker, _ = make_service(storage, client)

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert session["delta_context_packets"] == []
    assert all(event["type"] != "ask_delta_context_suggested" for event in broker.events)


def test_create_packet_manual_creates_user_packet(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, broker, _ = make_service(storage, FakeCodexClient())

    response = service.create_packet(project_id, root_id, "Scope", "Need to pin API version.", ["msg_1"])

    packet = response["packet"]
    stored = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]
    assert packet["suggested_by"] == "user"
    assert packet["status"] == "pending"
    assert packet["source_message_ids"] == ["msg_1"]
    assert stored["packet_id"] == packet["packet_id"]
    assert broker.events[-1]["type"] == "ask_delta_context_suggested"


def test_create_packet_rejects_when_planning_active(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.thread_store.set_planning_status(project_id, root_id, status="active", active_turn_id="planturn_1")
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(AskBlockedByPlanningActive):
        service.create_packet(project_id, root_id, "Scope", "Need more detail.")


def test_create_packet_rejects_after_split(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    attach_active_child(storage, project_id, root_id)
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(PacketMutationBlockedBySplit):
        service.create_packet(project_id, root_id, "Scope", "Need more detail.")


def test_approve_packet_transitions_pending_to_approved(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, broker, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]

    response = service.approve_packet(project_id, root_id, packet["packet_id"])

    approved = response["packet"]
    assert approved["status"] == "approved"
    assert approved["status_reason"] is None
    assert broker.events[-1]["type"] == "ask_packet_status_changed"


def test_approve_packet_raises_packet_not_found(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(PacketNotFound):
        service.approve_packet(project_id, root_id, "missing")


def test_approve_packet_rejects_after_split(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]
    attach_active_child(storage, project_id, root_id)

    with pytest.raises(PacketMutationBlockedBySplit):
        service.approve_packet(project_id, root_id, packet["packet_id"])


def test_reject_packet_transitions_pending_to_rejected(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, broker, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]

    response = service.reject_packet(project_id, root_id, packet["packet_id"])

    rejected = response["packet"]
    assert rejected["status"] == "rejected"
    assert rejected["status_reason"] == "Rejected by user"
    assert broker.events[-1]["type"] == "ask_packet_status_changed"


def test_reject_packet_transitions_approved_to_rejected(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]

    rejected = service.reject_packet(project_id, root_id, approved["packet_id"])["packet"]

    assert rejected["status"] == "rejected"
    assert rejected["status_reason"] == "Rejected by user"


def test_reject_packet_rejects_terminal_statuses(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]
    rejected = service.reject_packet(project_id, root_id, packet["packet_id"])["packet"]

    with pytest.raises(InvalidPacketTransition):
        service.reject_packet(project_id, root_id, rejected["packet_id"])


def test_reject_packet_allows_cleanup_after_split_for_approved_packet(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need more detail.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    attach_active_child(storage, project_id, root_id)

    rejected = service.reject_packet(project_id, root_id, packet["packet_id"])["packet"]

    assert rejected["status"] == "rejected"


def test_list_packets_returns_all_packets(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    first = service.create_packet(project_id, root_id, "One", "First.")["packet"]
    second = service.create_packet(project_id, root_id, "Two", "Second.")["packet"]

    packets = service.list_packets(project_id, root_id)["packets"]

    assert [packet["packet_id"] for packet in packets] == [first["packet_id"], second["packet_id"]]


def test_merge_packet_transitions_approved_to_merged(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, broker, thread_service = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]

    merged = service.merge_packet(project_id, root_id, approved["packet_id"])["packet"]

    assert thread_service.calls == [(project_id, root_id)]
    assert merged["status"] == "merged"
    assert merged["merged_at"] is not None
    assert isinstance(merged["merged_planning_turn_id"], str)
    assert broker.events[-1]["type"] == "ask_packet_status_changed"
    assert broker.events[-1]["packet"]["status"] == "merged"


def test_merge_packet_appends_context_merge_planning_turn(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]

    merged = service.merge_packet(project_id, root_id, approved["packet_id"])["packet"]
    planning_turns = storage.thread_store.get_planning_turns(project_id, root_id)
    merge_turn = planning_turns[-1]

    assert merge_turn["role"] == "context_merge"
    assert merge_turn["packet_id"] == packet["packet_id"]
    assert merge_turn["content"] == "Need stable API."
    assert merge_turn["summary"] == "Scope"
    assert merge_turn["turn_id"] == merged["merged_planning_turn_id"]
    assert merge_turn["is_inherited"] is False


def test_merge_packet_appends_clarified_answers_to_briefing(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]

    service.merge_packet(project_id, root_id, approved["packet_id"])

    briefing = storage.node_store.load_briefing(project_id, root_id)
    assert "**Scope**" in briefing["clarified_answers"]
    assert "Need stable API." in briefing["clarified_answers"]


def test_merge_packet_calls_codex_with_summary_and_context(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, _ = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]

    service.merge_packet(project_id, root_id, approved["packet_id"])

    merge_call = client.run_turn_calls[-1]
    assert merge_call["thread_id"] == "planning_1"
    assert "Summary: Scope" in str(merge_call["prompt"])
    assert "Need stable API." in str(merge_call["prompt"])


def test_merge_rejects_pending_packet(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]

    with pytest.raises(InvalidPacketTransition):
        service.merge_packet(project_id, root_id, packet["packet_id"])


def test_merge_rejects_rejected_packet(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    rejected = service.reject_packet(project_id, root_id, packet["packet_id"])["packet"]

    with pytest.raises(InvalidPacketTransition):
        service.merge_packet(project_id, root_id, rejected["packet_id"])


def test_merge_rejects_already_merged_packet(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    approved = service.approve_packet(project_id, root_id, packet["packet_id"])["packet"]
    merged = service.merge_packet(project_id, root_id, approved["packet_id"])["packet"]

    with pytest.raises(InvalidPacketTransition):
        service.merge_packet(project_id, root_id, merged["packet_id"])


def test_merge_rejects_when_node_has_active_children(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    attach_active_child(storage, project_id, root_id)

    with pytest.raises(MergeBlockedBySplit):
        service.merge_packet(project_id, root_id, packet["packet_id"])


def test_merge_rejects_done_node(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    mark_node(storage, project_id, root_id, status="done")

    with pytest.raises(AskThreadReadOnly):
        service.merge_packet(project_id, root_id, packet["packet_id"])


def test_merge_rejects_when_planning_active(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    mark_node(storage, project_id, root_id, planning_thread_id="planning_existing")
    storage.thread_store.set_planning_status(project_id, root_id, status="active", active_turn_id="planturn_1")

    with pytest.raises(AskBlockedByPlanningActive):
        service.merge_packet(project_id, root_id, packet["packet_id"])


def test_merge_rejects_when_ask_turn_active(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    storage.thread_store.set_ask_status(project_id, root_id, status="active", active_turn_id="askturn_1")

    with pytest.raises(AskTurnAlreadyActive):
        service.merge_packet(project_id, root_id, packet["packet_id"])


def test_merge_post_check_detects_out_of_band_split_during_codex_call(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, _ = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])

    client.on_run_turn = lambda: attach_active_child(storage, project_id, root_id)

    with pytest.raises(MergeBlockedBySplit):
        service.merge_packet(project_id, root_id, packet["packet_id"])

    planning_state = storage.thread_store.peek_node_state(project_id, root_id)["planning"]
    assert planning_state["status"] == "idle"
    assert planning_state["active_turn_id"] is None


def test_merge_packet_not_found(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service, _, _ = make_service(storage, FakeCodexClient())

    with pytest.raises(PacketNotFound):
        service.merge_packet(project_id, root_id, "missing")


def test_merge_returns_503_when_existing_planning_thread_is_unavailable(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, _ = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    mark_node(storage, project_id, root_id, planning_thread_id="planning_stale")

    with pytest.raises(MergePlanningThreadUnavailable):
        service.merge_packet(project_id, root_id, packet["packet_id"])

    session = storage.thread_store.get_ask_state(project_id, root_id)
    assert session["delta_context_packets"][0]["status"] == "approved"


def test_merge_clears_planning_reservation_after_planning_thread_unavailable(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, _ = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])
    mark_node(storage, project_id, root_id, planning_thread_id="planning_stale")

    with pytest.raises(MergePlanningThreadUnavailable):
        service.merge_packet(project_id, root_id, packet["packet_id"])

    planning_state = storage.thread_store.peek_node_state(project_id, root_id)["planning"]
    assert planning_state["status"] == "idle"
    assert planning_state["active_turn_id"] is None


def test_merge_lazily_ensures_planning_thread_when_missing_locally(project_service, storage: Storage, workspace_root) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeCodexClient()
    service, _, thread_service = make_service(storage, client)
    packet = service.create_packet(project_id, root_id, "Scope", "Need stable API.")["packet"]
    service.approve_packet(project_id, root_id, packet["packet_id"])

    merged = service.merge_packet(project_id, root_id, packet["packet_id"])["packet"]

    assert thread_service.calls == [(project_id, root_id)]
    assert merged["status"] == "merged"
