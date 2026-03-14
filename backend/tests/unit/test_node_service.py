from __future__ import annotations

import pytest

from backend.errors.app_errors import CompleteNotAllowed, NodeCreateNotAllowed, NodeUpdateNotAllowed
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    project_service.set_workspace_root(workspace_root)
    return project_service.create_project("Alpha", "Ship phase 3")


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def set_node_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    internal_nodes(snapshot)[node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def seed_ask_packets(storage: Storage, project_id: str, node_id: str, *statuses: str) -> None:
    ask_state = storage.thread_store.get_ask_state(project_id, node_id)
    packets = []
    for index, status in enumerate(statuses, start=1):
        packets.append(
            {
                "packet_id": f"dctx_{index}",
                "node_id": node_id,
                "created_at": "2026-03-11T00:00:00Z",
                "source_message_ids": [],
                "summary": f"Packet {index}",
                "context_text": f"Context {index}",
                "status": status,
                "status_reason": None,
                "merged_at": None,
                "merged_planning_turn_id": None,
                "suggested_by": "user",
            }
        )
    ask_state["delta_context_packets"] = packets
    storage.thread_store.write_ask_session(project_id, node_id, ask_state)


def test_create_child_sets_first_ready_second_locked_and_downgrades_parent(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)

    first = node_service.create_child(project_id, root_id)
    second = node_service.create_child(project_id, root_id)

    root = internal_nodes(second)[root_id]
    children = [node for node in internal_nodes(second).values() if node["parent_id"] == root_id]
    children.sort(key=lambda node: node["display_order"])

    assert root["status"] == "draft"
    assert children[0]["status"] == "ready"
    assert children[0]["hierarchical_number"] == "1.1"
    assert children[1]["status"] == "locked"
    assert children[1]["hierarchical_number"] == "1.2"


def test_create_child_keeps_title_and_description_only_in_task_file(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    result = node_service.create_child(project_id, root_id)
    child_id = result["tree_state"]["active_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    child = internal_nodes(persisted)[child_id]

    assert "title" not in child
    assert "description" not in child
    assert storage.node_store.load_task(project_id, child_id) == {
        "title": "New Node",
        "purpose": "",
        "responsibility": "",
    }


def test_update_node_writes_task_but_not_tree_title_or_description(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    node_service.update_node(project_id, root_id, title="Renamed Root", description="Clarified goal")

    persisted = storage.project_store.load_snapshot(project_id)
    root = internal_nodes(persisted)[root_id]

    assert "title" not in root
    assert "description" not in root
    assert storage.node_store.load_task(project_id, root_id) == {
        "title": "Renamed Root",
        "purpose": "Clarified goal",
        "responsibility": "",
    }


def test_done_nodes_reject_edit_and_child_creation(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "done"
    storage.project_store.save_snapshot(project_id, persisted)

    with pytest.raises(NodeCreateNotAllowed):
        node_service.create_child(project_id, root_id)

    with pytest.raises(NodeUpdateNotAllowed):
        node_service.update_node(project_id, root_id, title="Renamed")


def test_create_child_cleans_up_node_files_when_snapshot_save_fails(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    def fail_save_snapshot(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage.project_store, "save_snapshot", fail_save_snapshot)

    with pytest.raises(OSError, match="disk full"):
        node_service.create_child(project_id, root_id)

    nodes_dir = storage.node_store.node_dir(project_id, root_id).parent
    assert sorted(path.name for path in nodes_dir.iterdir() if path.is_dir()) == [root_id]
    persisted = storage.project_store.load_snapshot(project_id)
    assert internal_nodes(persisted)[root_id]["child_ids"] == []


def test_set_active_node_is_noop_when_value_unchanged(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    save_calls: list[tuple[object, ...]] = []
    touch_calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        storage.project_store,
        "save_snapshot",
        lambda *args, **kwargs: save_calls.append(args),
    )
    monkeypatch.setattr(
        storage.project_store,
        "touch_meta",
        lambda *args, **kwargs: touch_calls.append(args),
    )

    result = node_service.set_active_node(project_id, root_id)

    assert result["tree_state"]["active_node_id"] == root_id
    assert save_calls == []
    assert touch_calls == []


def test_set_active_node_persists_when_value_changes(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    save_calls: list[tuple[object, ...]] = []
    touch_calls: list[tuple[object, ...]] = []
    original_save_snapshot = storage.project_store.save_snapshot
    original_touch_meta = storage.project_store.touch_meta

    def counting_save_snapshot(*args, **kwargs):
        save_calls.append(args)
        return original_save_snapshot(*args, **kwargs)

    def counting_touch_meta(*args, **kwargs):
        touch_calls.append(args)
        return original_touch_meta(*args, **kwargs)

    monkeypatch.setattr(storage.project_store, "save_snapshot", counting_save_snapshot)
    monkeypatch.setattr(storage.project_store, "touch_meta", counting_touch_meta)

    result = node_service.set_active_node(project_id, root_id)

    assert child_id is not None
    assert result["tree_state"]["active_node_id"] == root_id
    assert len(save_calls) == 1
    assert len(touch_calls) == 1
    persisted = storage.project_store.load_snapshot(project_id)
    assert persisted["tree_state"]["active_node_id"] == root_id


def test_set_active_node_none_only_persists_for_transitions(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    save_calls: list[tuple[object, ...]] = []
    touch_calls: list[tuple[object, ...]] = []
    original_save_snapshot = storage.project_store.save_snapshot
    original_touch_meta = storage.project_store.touch_meta

    def counting_save_snapshot(*args, **kwargs):
        save_calls.append(args)
        return original_save_snapshot(*args, **kwargs)

    def counting_touch_meta(*args, **kwargs):
        touch_calls.append(args)
        return original_touch_meta(*args, **kwargs)

    monkeypatch.setattr(storage.project_store, "save_snapshot", counting_save_snapshot)
    monkeypatch.setattr(storage.project_store, "touch_meta", counting_touch_meta)

    first_result = node_service.set_active_node(project_id, None)

    assert first_result["tree_state"]["active_node_id"] is None
    assert len(save_calls) == 1
    assert len(touch_calls) == 1

    save_calls.clear()
    touch_calls.clear()

    second_result = node_service.set_active_node(project_id, None)

    assert second_result["tree_state"]["active_node_id"] is None
    assert save_calls == []
    assert touch_calls == []


def test_complete_unlocks_sibling_cascades_and_clears_active_node(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    first = node_service.create_child(project_id, root_id)
    first_child_id = first["tree_state"]["active_node_id"]
    second = node_service.create_child(project_id, root_id)
    second_child_id = second["tree_state"]["active_node_id"]
    assert isinstance(first_child_id, str)
    assert isinstance(second_child_id, str)
    set_node_phase(storage, project_id, first_child_id, "ready_for_execution")
    set_node_phase(storage, project_id, second_child_id, "ready_for_execution")

    node_service.set_active_node(project_id, first_child_id)
    after_first_complete = node_service.complete_node(project_id, first_child_id)
    child_nodes = {
        node["node_id"]: node
        for node in internal_nodes(after_first_complete).values()
        if node["parent_id"] == root_id
    }

    assert after_first_complete["tree_state"]["active_node_id"] == second_child_id
    assert child_nodes[first_child_id]["status"] == "done"
    assert child_nodes[second_child_id]["status"] == "ready"

    after_second_complete = node_service.complete_node(project_id, second_child_id)
    root = internal_nodes(after_second_complete)[root_id]

    assert root["status"] == "done"


def test_complete_rejects_non_leaf_nodes(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)

    node_service.create_child(project_id, root_id)

    with pytest.raises(CompleteNotAllowed):
        node_service.complete_node(project_id, root_id)


class RecordingThreadService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.fork_calls: list[tuple[str, str, str]] = []

    def fork_planning_thread(self, project_id: str, source_node_id: str, target_node_id: str) -> None:
        self.fork_calls.append((project_id, source_node_id, target_node_id))
        snapshot = self.storage.project_store.load_snapshot(project_id)
        nodes = internal_nodes(snapshot)
        nodes[target_node_id]["planning_thread_id"] = "planning_child"
        self.storage.project_store.save_snapshot(project_id, snapshot)


def test_complete_node_skips_fork_when_snapshot_changes_before_verification(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)

    base_node_service = NodeService(storage, tree_service)
    first = base_node_service.create_child(project_id, root_id)
    first_child_id = first["tree_state"]["active_node_id"]
    second = base_node_service.create_child(project_id, root_id)
    second_child_id = second["tree_state"]["active_node_id"]
    assert isinstance(first_child_id, str)
    assert isinstance(second_child_id, str)
    set_node_phase(storage, project_id, first_child_id, "ready_for_execution")
    set_node_phase(storage, project_id, second_child_id, "ready_for_execution")

    recording_thread_service = RecordingThreadService(storage)
    node_service = NodeService(storage, tree_service, recording_thread_service)

    original_load_snapshot = storage.project_store.load_snapshot
    load_count = {"count": 0}

    def racing_load_snapshot(project_id_arg: str):
        snapshot_payload = original_load_snapshot(project_id_arg)
        load_count["count"] += 1
        if load_count["count"] == 2:
            mutated = original_load_snapshot(project_id_arg)
            mutated["tree_state"]["active_node_id"] = None
            storage.project_store.save_snapshot(project_id_arg, mutated)
            return mutated
        return snapshot_payload

    monkeypatch.setattr(storage.project_store, "load_snapshot", racing_load_snapshot)

    result = node_service.complete_node(project_id, first_child_id)

    assert recording_thread_service.fork_calls == []
    assert result["tree_state"]["active_node_id"] is None


def test_complete_node_blocks_pending_packets(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)
    set_node_phase(storage, project_id, root_id, "ready_for_execution")
    seed_ask_packets(storage, project_id, root_id, "pending")

    node_service.complete_node(project_id, root_id)

    packet = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]
    assert packet["status"] == "blocked"
    assert packet["status_reason"] == "Node completed"


def test_complete_node_blocks_approved_packets(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)
    set_node_phase(storage, project_id, root_id, "ready_for_execution")
    seed_ask_packets(storage, project_id, root_id, "approved")

    node_service.complete_node(project_id, root_id)

    packet = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]
    assert packet["status"] == "blocked"
    assert packet["status_reason"] == "Node completed"


def test_complete_node_leaves_merged_rejected_and_blocked_packets_unchanged(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)
    set_node_phase(storage, project_id, root_id, "ready_for_execution")
    seed_ask_packets(storage, project_id, root_id, "merged", "rejected", "blocked")

    node_service.complete_node(project_id, root_id)

    packets = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"]
    assert [packet["status"] for packet in packets] == ["merged", "rejected", "blocked"]
    assert packets[2]["status_reason"] is None


def test_complete_node_rejects_while_planning_active(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)
    set_node_phase(storage, project_id, root_id, "ready_for_execution")
    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        status="active",
        active_turn_id="planturn_1",
    )

    with pytest.raises(CompleteNotAllowed, match="planning is active"):
        node_service.complete_node(project_id, root_id)


def test_cascade_done_blocks_parent_packets(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    internal_nodes(persisted)[root_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, persisted)

    first = node_service.create_child(project_id, root_id)
    first_child_id = first["tree_state"]["active_node_id"]
    second = node_service.create_child(project_id, root_id)
    second_child_id = second["tree_state"]["active_node_id"]
    assert isinstance(first_child_id, str)
    assert isinstance(second_child_id, str)
    set_node_phase(storage, project_id, first_child_id, "ready_for_execution")
    set_node_phase(storage, project_id, second_child_id, "ready_for_execution")

    seed_ask_packets(storage, project_id, root_id, "approved")

    node_service.complete_node(project_id, first_child_id)
    before_cascade_packet = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]
    assert before_cascade_packet["status"] == "approved"

    node_service.complete_node(project_id, second_child_id)

    parent_packet = storage.thread_store.get_ask_state(project_id, root_id)["delta_context_packets"][0]
    assert parent_packet["status"] == "blocked"
    assert parent_packet["status_reason"] == "Node completed"
