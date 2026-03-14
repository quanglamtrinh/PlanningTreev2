from __future__ import annotations

import pytest

from backend.errors.app_errors import CompleteNotAllowed, NodeUpdateNotAllowed
from backend.services.chat_service import ChatService
from backend.services.project_service import ProjectService
from backend.services.thread_service import ThreadService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker


class FakeCodexClient:
    def __init__(self) -> None:
        self.available_threads: set[str] = set()
        self._planning_counter = 0
        self._execution_counter = 0

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise RuntimeError("missing thread")
        return {"thread_id": thread_id}

    def start_planning_thread(self, **_: object) -> dict[str, object]:
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(self, *_: object, thread_id: str, **__: object) -> dict[str, object]:
        self.available_threads.add(thread_id)
        return {"stdout": "bootstrapped", "thread_id": thread_id, "turn_id": "turn_bootstrap", "tool_calls": []}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, object]:
        if source_thread_id not in self.available_threads:
            raise RuntimeError("missing thread")
        self._execution_counter += 1
        thread_id = f"execution_{self._execution_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def send_prompt_streaming(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {"stdout": "ok", "thread_id": kwargs.get("thread_id") or "thread_1"}


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


def set_node_status(storage: Storage, project_id: str, node_id: str, status: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = status
    storage.project_store.save_snapshot(project_id, snapshot)


def test_advance_to_executing_rejects_non_ready_phase(
    project_service: ProjectService,
    node_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    with pytest.raises(NodeUpdateNotAllowed, match="ready_for_execution"):
        node_service.advance_to_executing(project_id, root_id)


def test_advance_to_executing_advances_ready_node_and_is_idempotent(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, root_id, "ready_for_execution")

    state = node_service.advance_to_executing(project_id, root_id)
    assert state["phase"] == "executing"

    repeated = node_service.advance_to_executing(project_id, root_id)
    assert repeated["phase"] == "executing"


def test_thread_service_create_execution_thread_requires_executing(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ThreadService(storage, tree_service, FakeCodexClient())

    with pytest.raises(NodeUpdateNotAllowed, match="executing"):
        service.create_execution_thread(project_id, root_id)


def test_chat_service_create_message_requires_executing(
    project_service: ProjectService,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ChatService(storage, FakeCodexClient(), ChatEventBroker())

    with pytest.raises(NodeUpdateNotAllowed, match="Start execution first"):
        service.create_message(project_id, root_id, "hello")


@pytest.mark.parametrize("phase", ["planning", "briefing_review", "spec_review"])
def test_complete_node_rejects_non_execution_phases(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
    phase: str,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_status(storage, project_id, root_id, "ready")
    set_node_phase(storage, project_id, root_id, phase)

    with pytest.raises(CompleteNotAllowed, match="ready_for_execution"):
        node_service.complete_node(project_id, root_id)


def test_complete_node_succeeds_in_ready_for_execution(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_status(storage, project_id, root_id, "ready")
    set_node_phase(storage, project_id, root_id, "ready_for_execution")

    snapshot = node_service.complete_node(project_id, root_id)

    assert snapshot["tree_state"]["node_index"][root_id]["status"] == "done"
    state = storage.node_store.load_state(project_id, root_id)
    assert state["phase"] == "closed"


def test_complete_node_succeeds_in_executing(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_node_status(storage, project_id, root_id, "in_progress")
    set_node_phase(storage, project_id, root_id, "executing")

    snapshot = node_service.complete_node(project_id, root_id)

    assert snapshot["tree_state"]["node_index"][root_id]["status"] == "done"
    state = storage.node_store.load_state(project_id, root_id)
    assert state["phase"] == "closed"
