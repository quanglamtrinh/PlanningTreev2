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
        "source_message_ids": ["msg-1"],
        "summary": summary,
        "context_text": f"Context for {packet_id}",
        "status": status,
        "status_reason": None,
        "merged_at": None,
        "merged_planning_turn_id": None,
        "suggested_by": "agent",
    }


def test_get_node_state_includes_ask_key(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))

    node_state = storage.thread_store.get_node_state(project_id, root_id)

    assert node_state["ask"] == {
        "thread_id": None,
        "forked_from_planning_thread_id": None,
        "status": None,
        "active_turn_id": None,
        "messages": [],
        "event_seq": 0,
        "delta_context_packets": [],
        "created_at": None,
    }


def test_peek_node_state_includes_ask_key_without_persisting(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    before = store.read_thread_state(project_id)
    node_state = store.peek_node_state(project_id, root_id)
    after = store.read_thread_state(project_id)

    assert before == {}
    assert after == {}
    assert node_state["ask"]["messages"] == []
    assert node_state["ask"]["delta_context_packets"] == []
    assert node_state["ask"]["event_seq"] == 0


def test_get_ask_state_returns_default_for_new_node(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))

    ask_state = storage.thread_store.get_ask_state(project_id, root_id)

    assert ask_state == {
        "thread_id": None,
        "forked_from_planning_thread_id": None,
        "status": None,
        "active_turn_id": None,
        "messages": [],
        "event_seq": 0,
        "delta_context_packets": [],
        "created_at": None,
    }


def test_write_ask_session_replaces_full_ask_payload(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    session = {
        "thread_id": "ask_1",
        "forked_from_planning_thread_id": "planning_1",
        "status": "idle",
        "active_turn_id": None,
        "messages": [
            {
                "message_id": "msg_1",
                "role": "user",
                "content": "What changed?",
                "status": "completed",
                "created_at": "2026-03-11T00:00:00Z",
                "updated_at": "2026-03-11T00:00:00Z",
                "error": None,
            }
        ],
        "event_seq": 7,
        "delta_context_packets": [make_packet("dctx_1")],
        "created_at": "2026-03-11T00:00:00Z",
    }

    written = store.write_ask_session(project_id, root_id, session)

    assert written == session
    assert store.get_ask_state(project_id, root_id) == session


def test_write_ask_session_does_not_auto_increment_event_seq(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    session = {
        "thread_id": "ask_1",
        "forked_from_planning_thread_id": "planning_1",
        "status": "idle",
        "active_turn_id": None,
        "messages": [],
        "event_seq": 3,
        "delta_context_packets": [],
        "created_at": "2026-03-11T00:00:00Z",
    }

    written = store.write_ask_session(project_id, root_id, session)

    assert written["event_seq"] == 3
    assert store.get_ask_state(project_id, root_id)["event_seq"] == 3


def test_write_ask_session_and_append_planning_turn_writes_both_sections(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store
    ask_session = {
        "thread_id": "ask_1",
        "forked_from_planning_thread_id": "planning_1",
        "status": "idle",
        "active_turn_id": None,
        "messages": [],
        "event_seq": 5,
        "delta_context_packets": [make_packet("dctx_1", status="merged")],
        "created_at": "2026-03-11T00:00:00Z",
    }
    planning_turn = {
        "turn_id": "mergeturn_1",
        "role": "context_merge",
        "content": "Important context",
        "summary": "Summary",
        "packet_id": "dctx_1",
        "timestamp": "2026-03-11T00:00:01Z",
        "is_inherited": False,
        "origin_node_id": root_id,
    }

    written = store.write_ask_session_and_append_planning_turn(
        project_id,
        root_id,
        ask_session=ask_session,
        planning_turn=planning_turn,
        planning_status="idle",
        planning_active_turn_id=None,
    )

    assert written["ask"] == ask_session
    assert store.get_ask_state(project_id, root_id) == ask_session
    planning_turns = store.get_planning_turns(project_id, root_id)
    assert planning_turns[-1] == planning_turn


def test_write_ask_session_and_append_planning_turn_increments_planning_event_seq_only(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store
    store.set_planning_status(project_id, root_id, status="active", active_turn_id="mergeturn_1")
    store.append_planning_turn(
        project_id,
        root_id,
        {
            "turn_id": "planturn_0",
            "role": "assistant",
            "content": "Existing",
            "timestamp": "2026-03-11T00:00:00Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        },
    )
    ask_session = store.get_ask_state(project_id, root_id)
    ask_session["event_seq"] = 3

    written = store.write_ask_session_and_append_planning_turn(
        project_id,
        root_id,
        ask_session=ask_session,
        planning_turn={
            "turn_id": "mergeturn_1",
            "role": "context_merge",
            "content": "Important context",
            "summary": "Summary",
            "packet_id": "dctx_1",
            "timestamp": "2026-03-11T00:00:01Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        },
        planning_status="idle",
        planning_active_turn_id=None,
    )

    assert written["ask"]["event_seq"] == 3
    assert store.get_ask_state(project_id, root_id)["event_seq"] == 3
    planning_state = store.peek_node_state(project_id, root_id)["planning"]
    assert planning_state["event_seq"] == 2


def test_write_ask_session_and_append_planning_turn_sets_planning_status_and_active_turn_id(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store
    store.set_planning_status(project_id, root_id, status="active", active_turn_id="mergeturn_1")

    written = store.write_ask_session_and_append_planning_turn(
        project_id,
        root_id,
        ask_session=store.get_ask_state(project_id, root_id),
        planning_turn={
            "turn_id": "mergeturn_1",
            "role": "context_merge",
            "content": "Important context",
            "summary": "Summary",
            "packet_id": "dctx_1",
            "timestamp": "2026-03-11T00:00:01Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        },
        planning_status="idle",
        planning_active_turn_id=None,
    )

    assert written["planning"]["status"] == "idle"
    assert written["planning"]["active_turn_id"] is None
    planning_state = store.peek_node_state(project_id, root_id)["planning"]
    assert planning_state["status"] == "idle"
    assert planning_state["active_turn_id"] is None


def test_set_ask_status_updates_fields_and_bumps_event_seq(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    ask_state = store.set_ask_status(
        project_id,
        root_id,
        thread_id="t1",
        forked_from_planning_thread_id="p1",
        status="idle",
        active_turn_id=None,
    )

    assert ask_state["thread_id"] == "t1"
    assert ask_state["forked_from_planning_thread_id"] == "p1"
    assert ask_state["status"] == "idle"
    assert ask_state["active_turn_id"] is None
    assert ask_state["event_seq"] == 1

    persisted = store.get_ask_state(project_id, root_id)
    assert persisted == ask_state


def test_set_ask_status_can_clear_fields_back_to_none(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.set_ask_status(
        project_id,
        root_id,
        thread_id="t1",
        forked_from_planning_thread_id="p1",
        status="idle",
        active_turn_id="askturn_1",
    )
    cleared = store.set_ask_status(
        project_id,
        root_id,
        thread_id=None,
        forked_from_planning_thread_id=None,
        status=None,
        active_turn_id=None,
    )

    assert cleared["thread_id"] is None
    assert cleared["forked_from_planning_thread_id"] is None
    assert cleared["status"] is None
    assert cleared["active_turn_id"] is None
    assert cleared["event_seq"] == 2


def test_set_ask_status_noop_does_not_bump_event_seq(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    first = store.set_ask_status(
        project_id,
        root_id,
        thread_id="t1",
        forked_from_planning_thread_id="p1",
        status="idle",
        active_turn_id=None,
    )
    second = store.set_ask_status(
        project_id,
        root_id,
        thread_id="t1",
        forked_from_planning_thread_id="p1",
        status="idle",
        active_turn_id=None,
    )

    assert first["event_seq"] == 1
    assert second["event_seq"] == 1


def test_append_ask_message_adds_message_and_increments_event_seq(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    first = store.append_ask_message(
        project_id,
        root_id,
        {
            "message_id": "msg_1",
            "role": "user",
            "content": "What are the risks?",
        },
    )
    second = store.append_ask_message(
        project_id,
        root_id,
        {
            "message_id": "msg_2",
            "role": "assistant",
            "content": "Dependency risk.",
        },
    )

    assert len(first["messages"]) == 1
    assert first["event_seq"] == 1
    assert len(second["messages"]) == 2
    assert second["event_seq"] == 2


def test_upsert_delta_context_packet_insert_new_packet(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    inserted = store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1"))
    ask_state = store.get_ask_state(project_id, root_id)

    assert inserted["packet_id"] == "dctx_1"
    assert len(ask_state["delta_context_packets"]) == 1
    assert ask_state["event_seq"] == 1


def test_upsert_delta_context_packet_update_existing_packet(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="pending"))
    updated = store.upsert_delta_context_packet(
        project_id,
        root_id,
        make_packet("dctx_1", status="approved", summary="Updated"),
    )
    ask_state = store.get_ask_state(project_id, root_id)

    assert len(ask_state["delta_context_packets"]) == 1
    assert updated["status"] == "approved"
    assert updated["summary"] == "Updated"
    assert ask_state["event_seq"] == 2


def test_upsert_delta_context_packet_noop_does_not_bump_event_seq(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store
    packet = make_packet("dctx_1")

    first = store.upsert_delta_context_packet(project_id, root_id, packet)
    second = store.upsert_delta_context_packet(project_id, root_id, packet)

    assert first["packet_id"] == "dctx_1"
    assert store.get_ask_state(project_id, root_id)["event_seq"] == 1
    assert second["packet_id"] == "dctx_1"


def test_block_mergeable_ask_packets_blocks_pending_and_approved(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="pending"))
    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_2", status="approved"))
    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_3", status="merged"))

    blocked_count = store.block_mergeable_ask_packets(
        project_id,
        root_id,
        reason="Node was split",
    )
    ask_state = store.get_ask_state(project_id, root_id)
    packets = {packet["packet_id"]: packet for packet in ask_state["delta_context_packets"]}

    assert blocked_count == 2
    assert packets["dctx_1"]["status"] == "blocked"
    assert packets["dctx_1"]["status_reason"] == "Node was split"
    assert packets["dctx_2"]["status"] == "blocked"
    assert packets["dctx_2"]["status_reason"] == "Node was split"
    assert packets["dctx_3"]["status"] == "merged"
    assert ask_state["event_seq"] == 4


def test_block_mergeable_ask_packets_noop_when_no_mergeable_packets(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_1", status="merged"))
    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_2", status="rejected"))
    store.upsert_delta_context_packet(project_id, root_id, make_packet("dctx_3", status="blocked"))
    before = store.get_ask_state(project_id, root_id)

    blocked_count = store.block_mergeable_ask_packets(
        project_id,
        root_id,
        reason="Node was split",
    )
    after = store.get_ask_state(project_id, root_id)

    assert blocked_count == 0
    assert after == before
    assert after["event_seq"] == 3
