from __future__ import annotations

import copy

from backend.services.node_service import NodeService
from backend.ai.codex_client import CodexTransportError
from backend.services.project_service import ProjectService
from backend.services.thread_service import PLANNING_STALE_TURN_ERROR, ThreadService
from backend.storage.storage import Storage


class FakeCodexClient:
    def __init__(self) -> None:
        self.available_threads: set[str] = set()
        self.fail_once_on_fork: set[str] = set()
        self.resume_calls: list[str] = []
        self.start_calls: list[dict[str, object]] = []
        self.bootstrap_calls: list[str] = []
        self.fork_calls: list[str] = []
        self._planning_counter = 0
        self._execution_counter = 0

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self.resume_calls.append(thread_id)
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        return {"thread_id": thread_id}

    def start_planning_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools: list[dict[str, object]],
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.start_calls.append(
            {
                "thread_id": thread_id,
                "cwd": cwd,
                "base_instructions": base_instructions,
                "dynamic_tools": copy.deepcopy(dynamic_tools),
            }
        )
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(
        self,
        input_text: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
    ) -> dict[str, object]:
        self.bootstrap_calls.append(thread_id)
        self.available_threads.add(thread_id)
        return {
            "stdout": "bootstrap ok",
            "thread_id": thread_id,
            "turn_id": "turn_bootstrap",
            "tool_calls": [],
        }

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        self.fork_calls.append(source_thread_id)
        if source_thread_id not in self.available_threads or source_thread_id in self.fail_once_on_fork:
            self.fail_once_on_fork.discard(source_thread_id)
            raise CodexTransportError(
                f"no rollout found for thread id {source_thread_id}",
                "rpc_error",
            )
        self._execution_counter += 1
        thread_id = f"execution_{self._execution_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def set_node_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    internal_nodes(snapshot)[node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def test_create_execution_thread_reuses_existing_execution_session(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, node_id, "executing")
    client = FakeCodexClient()
    client.available_threads.add("execution_existing")
    service = ThreadService(storage, tree_service, client)

    session = {
        "project_id": project_id,
        "node_id": node_id,
        "thread_id": "execution_existing",
        "active_turn_id": None,
        "event_seq": 4,
        "status": "idle",
        "messages": [{"message_id": "msg_1", "role": "assistant", "content": "done"}],
        "config": {
            "access_mode": "project_write",
            "cwd": str(workspace_root),
            "writable_roots": [str(workspace_root)],
            "timeout_sec": 120,
        },
    }
    storage.thread_store.write_execution_session(project_id, node_id, session)

    response = service.create_execution_thread(project_id, node_id)

    assert response["thread_id"] == "execution_existing"
    assert response["session"]["thread_id"] == "execution_existing"
    assert response["session"]["messages"] == session["messages"]
    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[node_id]
    assert root["execution_thread_id"] == "execution_existing"
    assert client.start_calls == []
    assert client.fork_calls == []


def test_create_execution_thread_preserves_plan_mode_session_fields(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, node_id, "ready_for_execution")
    client = FakeCodexClient()
    client.available_threads.add("planning_1")
    client.available_threads.add("execution_existing")
    service = ThreadService(storage, tree_service, client)

    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[node_id]
    root["planning_thread_id"] = "planning_1"
    root["execution_thread_id"] = "execution_existing"
    storage.project_store.save_snapshot(project_id, snapshot)

    session = {
        "project_id": project_id,
        "node_id": node_id,
        "thread_id": "execution_existing",
        "active_turn_id": None,
        "event_seq": 7,
        "status": "idle",
        "mode": "plan",
        "plan_message_start_index": 4,
        "messages": [{"message_id": "msg_1", "role": "assistant", "content": "question"}],
        "config": {
            "access_mode": "project_write",
            "cwd": str(workspace_root),
            "writable_roots": [str(workspace_root)],
            "timeout_sec": 120,
        },
    }
    storage.thread_store.write_execution_session(project_id, node_id, session)

    response = service.create_execution_thread(project_id, node_id)

    assert response["thread_id"] == "execution_existing"
    assert response["session"]["mode"] == "plan"
    assert response["session"]["plan_message_start_index"] == 4
    persisted = storage.thread_store.get_execution_session(project_id, node_id)
    assert persisted["mode"] == "plan"
    assert persisted["plan_message_start_index"] == 4


def test_create_execution_thread_recreates_stale_planning_thread(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, node_id = create_project(project_service, str(workspace_root))
    set_node_phase(storage, project_id, node_id, "executing")
    client = FakeCodexClient()
    service = ThreadService(storage, tree_service, client)

    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[node_id]
    root["planning_thread_id"] = "planning_stale"
    root["planning_thread_bootstrapped_at"] = None
    storage.project_store.save_snapshot(project_id, snapshot)

    client.fail_once_on_fork.add("planning_1")

    response = service.create_execution_thread(project_id, node_id)

    assert response["thread_id"] == "execution_1"
    assert client.start_calls[0]["thread_id"] == "planning_1"
    assert client.start_calls[1]["thread_id"] == "planning_2"
    assert client.bootstrap_calls == ["planning_2"]

    updated_snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(updated_snapshot)[node_id]
    assert root["planning_thread_id"] == "planning_2"
    assert root["execution_thread_id"] == "execution_1"
    assert isinstance(root["planning_thread_bootstrapped_at"], str)


def test_fork_planning_thread_materializes_inherited_history_once(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    node_service = NodeService(storage, tree_service)
    project_id, root_id = create_project(project_service, str(workspace_root))
    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    assert isinstance(child_id, str)

    client = FakeCodexClient()
    client.available_threads.add("planning_root")
    service = ThreadService(storage, tree_service, client)

    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[root_id]
    root["planning_thread_id"] = "planning_root"
    storage.project_store.save_snapshot(project_id, snapshot)
    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        thread_id="planning_root",
        forked_from_node=None,
        status="idle",
        active_turn_id=None,
    )
    service.append_visible_planning_turn(
        project_id,
        root_id,
        turn_id="turn_root",
        user_content="Split this node",
        tool_calls=[
            {
                "tool_name": "emit_render_data",
                "arguments": {"kind": "split_result", "payload": {"subtasks": [{"order": 1, "prompt": "One"}]}},
            }
        ],
        assistant_content="Here is the split.",
        timestamp="2026-03-10T00:00:00Z",
    )
    root_turns = storage.thread_store.get_planning_turns(project_id, root_id)

    service.fork_planning_thread(project_id, root_id, child_id)
    first_turns = storage.thread_store.get_planning_turns(project_id, child_id)
    service.fork_planning_thread(project_id, root_id, child_id)
    second_turns = storage.thread_store.get_planning_turns(project_id, child_id)

    assert len(first_turns) == 3
    assert all(turn["is_inherited"] is False for turn in root_turns)
    assert all(turn["origin_node_id"] == root_id for turn in root_turns)
    assert first_turns == second_turns
    assert all(turn["is_inherited"] is True for turn in first_turns)
    assert all(turn["origin_node_id"] == root_id for turn in first_turns)


def test_grandchild_inherits_full_lineage_without_rewriting_origin_node_id(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    node_service = NodeService(storage, tree_service)
    project_id, root_id = create_project(project_service, str(workspace_root))
    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    assert isinstance(child_id, str)
    grandchild_snapshot = node_service.create_child(project_id, child_id)
    grandchild_id = grandchild_snapshot["tree_state"]["active_node_id"]
    assert isinstance(grandchild_id, str)

    client = FakeCodexClient()
    client.available_threads.add("planning_root")
    service = ThreadService(storage, tree_service, client)

    snapshot = storage.project_store.load_snapshot(project_id)
    nodes = internal_nodes(snapshot)
    nodes[root_id]["planning_thread_id"] = "planning_root"
    storage.project_store.save_snapshot(project_id, snapshot)
    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        thread_id="planning_root",
        forked_from_node=None,
        status="idle",
        active_turn_id=None,
    )
    service.append_visible_planning_turn(
        project_id,
        root_id,
        turn_id="turn_root",
        user_content="Root user",
        tool_calls=[],
        assistant_content="Root assistant",
        timestamp="2026-03-10T00:00:00Z",
    )

    service.fork_planning_thread(project_id, root_id, child_id)
    service.append_visible_planning_turn(
        project_id,
        child_id,
        turn_id="turn_child",
        user_content="Child user",
        tool_calls=[],
        assistant_content="Child assistant",
        timestamp="2026-03-10T00:01:00Z",
    )

    child_snapshot = storage.project_store.load_snapshot(project_id)
    child_node = internal_nodes(child_snapshot)[child_id]
    child_thread_id = child_node["planning_thread_id"]
    assert isinstance(child_thread_id, str)
    client.available_threads.add(child_thread_id)

    service.fork_planning_thread(project_id, child_id, grandchild_id)
    grandchild_turns = storage.thread_store.get_planning_turns(project_id, grandchild_id)

    assert [turn["origin_node_id"] for turn in grandchild_turns] == [
        root_id,
        root_id,
        child_id,
        child_id,
    ]
    assert all(turn["is_inherited"] is True for turn in grandchild_turns)


def test_materialize_planning_history_backfills_legacy_forked_node(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    node_service = NodeService(storage, tree_service)
    project_id, root_id = create_project(project_service, str(workspace_root))
    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    assert isinstance(child_id, str)

    client = FakeCodexClient()
    service = ThreadService(storage, tree_service, client)

    service.append_visible_planning_turn(
        project_id,
        root_id,
        turn_id="turn_root",
        user_content="Root user",
        tool_calls=[],
        assistant_content="Root assistant",
        timestamp="2026-03-10T00:00:00Z",
    )

    snapshot = storage.project_store.load_snapshot(project_id)
    child = internal_nodes(snapshot)[child_id]
    child["planning_thread_forked_from_node"] = root_id
    storage.project_store.save_snapshot(project_id, snapshot)
    storage.thread_store.set_planning_status(
        project_id,
        child_id,
        thread_id="planning_child",
        forked_from_node=root_id,
        status="idle",
        active_turn_id=None,
    )

    turns = service.materialize_inherited_planning_history(project_id, child_id)

    assert len(turns) == 2
    assert all(turn["is_inherited"] is True for turn in turns)
    assert all(turn["origin_node_id"] == root_id for turn in turns)


def test_reconcile_interrupted_planning_turns_resets_active_status_and_appends_failure_turn(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ThreadService(storage, tree_service, FakeCodexClient())

    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        thread_id="planning_root",
        forked_from_node=None,
        status="active",
        active_turn_id="turn_stale",
    )

    service.reconcile_interrupted_planning_turns()

    planning = storage.thread_store.get_node_state(project_id, root_id)["planning"]
    assert planning["status"] == "idle"
    assert planning["active_turn_id"] is None
    assert planning["turns"][-1]["turn_id"] == "turn_stale"
    assert planning["turns"][-1]["role"] == "assistant"
    assert planning["turns"][-1]["content"] == PLANNING_STALE_TURN_ERROR
    assert planning["turns"][-1]["is_inherited"] is False
    assert planning["turns"][-1]["origin_node_id"] == root_id


def test_reconcile_interrupted_planning_turns_does_not_duplicate_terminal_assistant_turn(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ThreadService(storage, tree_service, FakeCodexClient())

    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        thread_id="planning_root",
        forked_from_node=None,
        status="active",
        active_turn_id="turn_existing",
    )
    storage.thread_store.append_planning_turn(
        project_id,
        root_id,
        {
            "turn_id": "turn_existing",
            "role": "assistant",
            "content": "Already failed.",
            "timestamp": "2026-03-10T00:00:00Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        },
    )

    service.reconcile_interrupted_planning_turns()

    planning = storage.thread_store.get_node_state(project_id, root_id)["planning"]
    assistant_turns = [
        turn
        for turn in planning["turns"]
        if turn["turn_id"] == "turn_existing" and turn["role"] == "assistant"
    ]
    assert planning["status"] == "idle"
    assert planning["active_turn_id"] is None
    assert len(assistant_turns) == 1


def test_materialize_planning_history_uses_peek_node_state_not_write_through_accessor(
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    node_service = NodeService(storage, tree_service)
    project_id, root_id = create_project(project_service, str(workspace_root))
    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    assert isinstance(child_id, str)

    service = ThreadService(storage, tree_service, FakeCodexClient())
    service.append_visible_planning_turn(
        project_id,
        root_id,
        turn_id="turn_root",
        user_content="Root user",
        tool_calls=[],
        assistant_content="Root assistant",
        timestamp="2026-03-10T00:00:00Z",
    )

    snapshot = storage.project_store.load_snapshot(project_id)
    child = internal_nodes(snapshot)[child_id]
    child["planning_thread_forked_from_node"] = root_id
    storage.project_store.save_snapshot(project_id, snapshot)

    monkeypatch.setattr(
        storage.thread_store,
        "get_node_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("materialize should not use write-through get_node_state")
        ),
    )

    turns = service.materialize_inherited_planning_history(project_id, child_id)

    assert len(turns) == 2
    assert all(turn["origin_node_id"] == root_id for turn in turns)


def test_ensure_planning_thread_checks_availability_outside_project_lock(
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = ThreadService(storage, tree_service, FakeCodexClient())

    snapshot = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(snapshot)[root_id]
    root["planning_thread_id"] = "planning_existing"
    storage.project_store.save_snapshot(project_id, snapshot)

    project_lock = storage.project_lock(project_id)

    def fake_thread_is_available(thread_id: str, workspace_root_arg: str | None) -> bool:
        is_owned = getattr(project_lock, "_is_owned", None)
        assert callable(is_owned)
        assert is_owned() is False
        assert thread_id == "planning_existing"
        return True

    monkeypatch.setattr(service, "_thread_is_available", fake_thread_is_available)

    thread_id = service.ensure_planning_thread(project_id, root_id)

    assert thread_id == "planning_existing"
