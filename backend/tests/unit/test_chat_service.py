from __future__ import annotations

import threading
import time

import pytest

from backend.errors.app_errors import ChatTurnAlreadyActive
from backend.services.chat_service import STALE_TURN_ERROR, ChatService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker


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
        if callable(on_delta):
            on_delta("hello ")
        self.started.set()
        if self.block_event is not None:
            self.block_event.wait(timeout=5)
        if self.raise_error is not None:
            raise self.raise_error
        if callable(on_delta):
            on_delta("world")
        return {"stdout": "hello world", "thread_id": thread_id or "thread_1"}


def create_project(project_service, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def mark_root_ready(storage: Storage, project_id: str, root_id: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[root_id]
    root["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snapshot)


def set_node_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    internal_nodes(snapshot)[node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def write_invalid_task(storage: Storage, project_id: str, node_id: str) -> None:
    task_path = storage.node_store.node_dir(project_id, node_id) / "task.md"
    task_path.write_text("# Task\n\n## Title\nBroken\n\n## Title\nStill broken\n", encoding="utf-8")


def wait_for_idle(storage: Storage, project_id: str, node_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = storage.chat_store.read_chat_state(project_id).get(node_id)
        if isinstance(session, dict) and session.get("active_turn_id") is None:
            return session
        time.sleep(0.02)
    raise AssertionError(f"chat session did not become idle for {node_id}")


def test_build_prompt_uses_empty_task_fields_when_task_document_is_invalid(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    write_invalid_task(storage, project_id, root_id)
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())
    snapshot = storage.project_store.load_snapshot(project_id)
    node = internal_nodes(snapshot)[root_id]

    prompt = service._build_prompt(
        project_id=project_id,
        snapshot=snapshot,
        node=node,
        workspace_root=str(workspace_root),
        config=service._default_config(str(workspace_root)),
        user_message="hello",
    )

    assert '"node_title": ""' in prompt
    assert '"node_description": ""' in prompt


def test_get_session_normalizes_empty_state(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())

    session = service.get_session(project_id, root_id)["session"]

    assert session["project_id"] == project_id
    assert session["node_id"] == root_id
    assert session["event_seq"] == 0
    assert session["messages"] == []
    assert session["config"]["access_mode"] == "project_write"
    assert storage.chat_store.read_chat_state(project_id)[root_id]["node_id"] == root_id
    assert "sessions" not in storage.chat_store.read_chat_state(project_id)


def test_create_message_promotes_ready_node_and_completes_turn(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_root_ready(storage, project_id, root_id)
    set_node_phase(storage, project_id, root_id, "executing")
    release = threading.Event()
    client = FakeCodexClient(block_event=release)
    service = ChatService(storage, client, ChatEventBroker())

    response = service.create_message(project_id, root_id, "hello")

    assert response["status"] == "accepted"
    assert client.started.wait(timeout=1)

    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[root_id]
    assert root["status"] == "in_progress"

    active_session = storage.chat_store.read_chat_state(project_id)[root_id]
    assert active_session["active_turn_id"] is not None
    assert active_session["event_seq"] >= 2
    assert active_session["messages"][-1]["status"] == "streaming"

    release.set()
    completed = wait_for_idle(storage, project_id, root_id)
    assert completed["event_seq"] == 4
    assert completed["thread_id"] == "thread_1"
    assert completed["messages"][-1]["status"] == "completed"
    assert completed["messages"][-1]["content"] == "hello world"


def test_get_session_recovers_stale_active_turn(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.chat_store.write_chat_state(
        project_id,
        {
            root_id: {
                "project_id": project_id,
                "node_id": root_id,
                "thread_id": "thread_1",
                "active_turn_id": "turn_1",
                "event_seq": 7,
                "config": {
                    "access_mode": "project_write",
                    "cwd": str(workspace_root),
                    "writable_roots": [str(workspace_root)],
                    "timeout_sec": 120,
                },
                "messages": [
                    {
                        "message_id": "msg_assistant",
                        "role": "assistant",
                        "content": "partial",
                        "status": "streaming",
                        "created_at": "2026-03-08T00:00:00Z",
                        "updated_at": "2026-03-08T00:00:01Z",
                        "error": None,
                    }
                ],
            }
        },
    )
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())

    session = service.get_session(project_id, root_id)["session"]

    assert session["active_turn_id"] is None
    assert session["event_seq"] == 7
    assert session["messages"][0]["status"] == "error"
    assert session["messages"][0]["error"] == STALE_TURN_ERROR


def test_get_session_keeps_live_turn_active(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, root_id, "executing")
    release = threading.Event()
    client = FakeCodexClient(block_event=release)
    service = ChatService(storage, client, ChatEventBroker())

    service.create_message(project_id, root_id, "hello")
    assert client.started.wait(timeout=1)

    session = service.get_session(project_id, root_id)["session"]

    assert session["active_turn_id"] is not None
    assert session["event_seq"] >= 2
    assert session["messages"][-1]["status"] in {"pending", "streaming"}
    assert session["messages"][-1]["error"] is None

    release.set()
    completed = wait_for_idle(storage, project_id, root_id)
    assert completed["messages"][-1]["status"] == "completed"
    assert completed["messages"][-1]["content"] == "hello world"


def test_reset_rejects_while_turn_is_active(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_root_ready(storage, project_id, root_id)
    set_node_phase(storage, project_id, root_id, "executing")
    release = threading.Event()
    client = FakeCodexClient(block_event=release)
    service = ChatService(storage, client, ChatEventBroker())

    service.create_message(project_id, root_id, "hello")
    assert client.started.wait(timeout=1)

    with pytest.raises(ChatTurnAlreadyActive):
        service.reset_session(project_id, root_id)

    release.set()
    wait_for_idle(storage, project_id, root_id)


def test_failed_turn_marks_assistant_message_error(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, root_id, "executing")
    service = ChatService(
        storage,
        FakeCodexClient(raise_error=RuntimeError("boom")),
        ChatEventBroker(),
    )

    service.create_message(project_id, root_id, "hello")
    session = wait_for_idle(storage, project_id, root_id)

    assert session["messages"][-1]["status"] == "error"
    assert "boom" in session["messages"][-1]["error"]
    assert session["event_seq"] == 3


def test_reconcile_interrupted_turns_recovers_active_sessions(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.chat_store.write_chat_state(
        project_id,
        {
            root_id: {
                "project_id": project_id,
                "node_id": root_id,
                "thread_id": "thread_1",
                "active_turn_id": "turn_1",
                "event_seq": 2,
                "config": {
                    "access_mode": "project_write",
                    "cwd": str(workspace_root),
                    "writable_roots": [str(workspace_root)],
                    "timeout_sec": 120,
                },
                "messages": [
                    {
                        "message_id": "msg_user",
                        "role": "user",
                        "content": "hello",
                        "status": "completed",
                        "created_at": "2026-03-08T00:00:00Z",
                        "updated_at": "2026-03-08T00:00:00Z",
                        "error": None,
                    },
                    {
                        "message_id": "msg_assistant",
                        "role": "assistant",
                        "content": "partial",
                        "status": "streaming",
                        "created_at": "2026-03-08T00:00:00Z",
                        "updated_at": "2026-03-08T00:00:01Z",
                        "error": None,
                    },
                ],
            }
        },
    )
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())

    service.reconcile_interrupted_turns()

    session = storage.chat_store.read_chat_state(project_id)[root_id]
    assert session["active_turn_id"] is None
    assert session["event_seq"] == 2
    assert session["messages"][-1]["status"] == "error"
    assert session["messages"][-1]["error"] == STALE_TURN_ERROR


def test_event_seq_advances_through_reset(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, root_id, "executing")
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())

    service.create_message(project_id, root_id, "hello")
    completed = wait_for_idle(storage, project_id, root_id)

    assert completed["event_seq"] == 4

    reset = service.reset_session(project_id, root_id)["session"]
    stored = storage.chat_store.read_chat_state(project_id)[root_id]

    assert reset["event_seq"] == 5
    assert reset["messages"] == []
    assert stored["thread_id"] == completed["thread_id"]
