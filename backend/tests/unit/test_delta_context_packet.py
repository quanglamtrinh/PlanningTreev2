from __future__ import annotations

from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def make_packet(packet_id: str, *, status: str = "pending", summary: str = "Summary") -> dict[str, object]:
    return {
        "packet_id": packet_id,
        "node_id": "node-1",
        "created_at": "2026-03-11T00:00:00Z",
        "source_message_ids": ["msg-1", "msg-2"],
        "summary": summary,
        "context_text": f"Context for {packet_id}",
        "status": status,
        "status_reason": None,
        "merged_at": None,
        "merged_planning_turn_id": None,
        "suggested_by": "agent",
    }


def test_packet_insert_preserves_all_fields(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store
    packet = make_packet("dctx_1", status="approved", summary="Constraint found")

    store.upsert_delta_context_packet(project_id, root_id, packet)
    ask_state = store.get_ask_state(project_id, root_id)

    assert ask_state["delta_context_packets"] == [packet]


def test_packet_upsert_replaces_by_packet_id(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="pending"))
    replacement = make_packet("dctx_1", status="approved", summary="Replacement")
    store.upsert_delta_context_packet(project_id, root_id, replacement)
    ask_state = store.get_ask_state(project_id, root_id)

    assert len(ask_state["delta_context_packets"]) == 1
    assert ask_state["delta_context_packets"][0] == replacement


def test_packet_upsert_appends_for_distinct_packet_ids(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    first = make_packet("dctx_1")
    second = make_packet("dctx_2", summary="Second")
    store.upsert_delta_context_packet(project_id, root_id, first)
    store.upsert_delta_context_packet(project_id, root_id, second)
    ask_state = store.get_ask_state(project_id, root_id)

    assert ask_state["delta_context_packets"] == [first, second]


def test_block_only_affects_pending_and_approved_packets(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    for packet in [
        make_packet("dctx_1", status="pending"),
        make_packet("dctx_2", status="approved"),
        make_packet("dctx_3", status="merged"),
        make_packet("dctx_4", status="rejected"),
        make_packet("dctx_5", status="blocked"),
    ]:
        store.upsert_delta_context_packet(project_id, root_id, packet)

    store.block_mergeable_ask_packets(project_id, root_id, reason="Node was split")
    packets = {
        packet["packet_id"]: packet for packet in store.get_ask_state(project_id, root_id)["delta_context_packets"]
    }

    assert packets["dctx_1"]["status"] == "blocked"
    assert packets["dctx_2"]["status"] == "blocked"
    assert packets["dctx_3"]["status"] == "merged"
    assert packets["dctx_4"]["status"] == "rejected"
    assert packets["dctx_5"]["status"] == "blocked"


def test_storage_layer_does_not_enforce_packet_transition_policy(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="merged"))
    # Transition validation belongs to AskService in a later phase.
    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="pending"))
    ask_state = store.get_ask_state(project_id, root_id)

    assert len(ask_state["delta_context_packets"]) == 1
    assert ask_state["delta_context_packets"][0]["status"] == "pending"
