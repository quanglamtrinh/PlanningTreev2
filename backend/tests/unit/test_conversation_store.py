from __future__ import annotations

from backend.conversation.contracts import (
    conversation_scope_key,
    make_conversation_message,
    make_conversation_part,
)
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def test_get_or_create_conversation_uses_one_canonical_scope_identity(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.conversation_store

    first = store.get_or_create_conversation(project_id, root_id, "execution", "execute")
    second = store.get_or_create_conversation(project_id, root_id, "execution", "execute")

    assert first["record"]["conversation_id"] == second["record"]["conversation_id"]
    state = store.read_conversation_state(project_id)
    scope_key = conversation_scope_key(project_id, root_id, "execution")
    assert state["scope_index"][scope_key] == first["record"]["conversation_id"]


def test_upsert_message_and_event_seq_persist_rich_conversation_state(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.conversation_store

    snapshot = store.get_or_create_conversation(project_id, root_id, "ask", "ask")
    conversation_id = snapshot["record"]["conversation_id"]
    message = make_conversation_message(
        conversation_id=conversation_id,
        turn_id="turn_1",
        role="assistant",
        runtime_mode="ask",
        status="streaming",
        parts=[
            make_conversation_part(
                part_type="assistant_text",
                order=0,
                status="streaming",
                payload={"content": "hello"},
            )
        ],
    )

    store.upsert_message(project_id, conversation_id, message)
    store.set_active_stream(project_id, conversation_id, "stream_1")
    store.advance_event_seq(project_id, conversation_id, 4)

    persisted = store.get_conversation(project_id, conversation_id)
    assert persisted is not None
    assert persisted["record"]["active_stream_id"] == "stream_1"
    assert persisted["record"]["event_seq"] == 4
    assert persisted["messages"][0]["parts"][0]["part_type"] == "assistant_text"
    assert persisted["messages"][0]["parts"][0]["payload"]["content"] == "hello"
