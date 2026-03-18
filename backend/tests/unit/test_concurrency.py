from __future__ import annotations

import threading
import time

from backend.services.chat_service import ChatService
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker, PlanningEventBroker


class BlockingSplitClient:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

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
        self.started.set()
        self.release.wait(timeout=5)
        response = {
            "stdout": """
            {
              "subtasks": [
                {"id": "S1", "title": "First step", "objective": "Prepare the first step", "why_now": "This starts the flow."},
                {"id": "S2", "title": "Second step", "objective": "Deliver the second step", "why_now": "This follows the foundation."},
                {"id": "S3", "title": "Third step", "objective": "Finish the flow", "why_now": "This completes the canonical workflow."}
              ]
            }
            """,
            "thread_id": thread_id or "thread_split",
            "tool_calls": [
                {
                    "tool_name": "emit_render_data",
                    "arguments": {
                        "kind": "split_result",
                        "payload": {
                            "subtasks": [
                                {"id": "S1", "title": "First step", "objective": "Prepare the first step", "why_now": "This starts the flow."},
                                {"id": "S2", "title": "Second step", "objective": "Deliver the second step", "why_now": "This follows the foundation."},
                                {"id": "S3", "title": "Third step", "objective": "Finish the flow", "why_now": "This completes the canonical workflow."},
                            ]
                        },
                    },
                }
            ],
        }
        if callable(on_tool_call):
            for tool_call in response["tool_calls"]:
                arguments = tool_call.get("arguments")
                if isinstance(arguments, dict):
                    on_tool_call(str(tool_call.get("tool_name") or ""), arguments)
        return response


class ImmediateChatClient:
    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
    ) -> dict[str, object]:
        if callable(on_delta):
            on_delta("hello ")
            on_delta("world")
        return {"stdout": "hello world", "thread_id": thread_id or "thread_chat"}


class FakeThreadService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def ensure_planning_thread(
        self,
        project_id: str,
        node_id: str,
        *,
        source_node_id: str | None = None,
    ) -> str:
        return "planning_1"

    def set_planning_status(
        self,
        project_id: str,
        node_id: str,
        *,
        status: str | None,
        active_turn_id: str | None,
    ) -> dict[str, object]:
        return self._storage.thread_store.set_planning_status(
            project_id,
            node_id,
            status=status,
            active_turn_id=active_turn_id,
        )

    def append_visible_planning_turn(
        self,
        project_id: str,
        node_id: str,
        *,
        turn_id: str,
        user_content: str,
        tool_calls: list[dict[str, object]],
        assistant_content: str,
        timestamp: str,
    ) -> list[dict[str, object]]:
        entries = [
            {
                "turn_id": turn_id,
                "role": "user",
                "content": user_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            },
            {
                "turn_id": turn_id,
                "role": "assistant",
                "content": assistant_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            },
        ]
        for entry in entries:
            self._storage.thread_store.append_planning_turn(project_id, node_id, entry)
        return entries

    def fork_planning_thread(self, project_id: str, source_node_id: str, target_node_id: str) -> str:
        return "planning_1"


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def set_node_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def wait_for_idle(storage: Storage, project_id: str, node_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = storage.chat_store.read_chat_state(project_id).get(node_id)
        if isinstance(session, dict) and session.get("active_turn_id") is None:
            return session
        time.sleep(0.02)
    raise AssertionError(f"chat session did not become idle for {node_id}")


def wait_for_split_completion(storage: Storage, project_id: str, node_id: str, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        planning = storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning.get("active_turn_id") is None and str(planning.get("status") or "") != "active":
            return
        time.sleep(0.02)
    raise AssertionError(f"split did not complete for {node_id}")


def test_split_preserves_concurrent_snapshot_and_chat_updates(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    split_client = BlockingSplitClient()
    split_service = SplitService(
        storage,
        tree_service,
        split_client,
        thread_service=FakeThreadService(storage),
        planning_event_broker=PlanningEventBroker(),
        split_timeout=5,
    )
    node_service = NodeService(storage, tree_service)
    chat_service = ChatService(storage, ImmediateChatClient(), ChatEventBroker())
    split_errors: list[Exception] = []

    def run_split() -> None:
        try:
            split_service.split_node(project_id, root_id, "workflow")
        except Exception as exc:  # pragma: no cover - test should fail below if this happens
            split_errors.append(exc)

    worker = threading.Thread(target=run_split)
    worker.start()

    assert split_client.started.wait(timeout=1)

    node_service.update_node(project_id, root_id, title="Renamed Root")
    set_node_phase(storage, project_id, root_id, "executing")
    chat_service.create_message(project_id, root_id, "hello")
    chat_session = wait_for_idle(storage, project_id, root_id)

    split_client.release.set()
    worker.join(timeout=5)
    wait_for_split_completion(storage, project_id, root_id)

    assert not split_errors
    final_snapshot = storage.project_store.load_snapshot(project_id)
    root = final_snapshot["tree_state"]["node_index"][root_id]
    meta = storage.project_store.load_meta(project_id)

    assert "title" not in root
    assert storage.node_store.load_task(project_id, root_id)["title"] == "Renamed Root"
    assert root["planning_mode"] == "workflow"
    assert root["split_metadata"]["created_child_ids"]
    assert chat_session["messages"][-1]["status"] == "completed"
    assert chat_session["thread_id"] == "thread_chat"
    assert meta["updated_at"] == final_snapshot["updated_at"]
