from __future__ import annotations

from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def test_get_node_state_does_not_route_through_public_read_write_methods(
    storage: Storage,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    monkeypatch.setattr(
        store,
        "read_thread_state",
        lambda project_id: (_ for _ in ()).throw(AssertionError("public read_thread_state should not be reused")),
    )
    monkeypatch.setattr(
        store,
        "write_thread_state",
        lambda project_id, payload: (_ for _ in ()).throw(
            AssertionError("public write_thread_state should not be reused")
        ),
    )

    node_state = store.get_node_state(project_id, root_id)

    assert node_state["planning"]["turns"] == []
    assert node_state["execution"]["messages"] == []


def test_peek_node_state_returns_defaults_without_persisting_missing_node_state(
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
    assert node_state["planning"]["turns"] == []
    assert node_state["execution"]["messages"] == []


def test_append_and_replace_planning_turns_preserve_thread_state_shape(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    store = storage.thread_store

    store.append_planning_turn(
        project_id,
        root_id,
        {
            "turn_id": "turn_1",
            "role": "assistant",
            "content": "First",
            "timestamp": "2026-03-10T00:00:00Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        },
    )
    store.replace_planning_turns(
        project_id,
        root_id,
        [
            {
                "turn_id": "turn_2",
                "role": "assistant",
                "content": "Second",
                "timestamp": "2026-03-10T00:01:00Z",
                "is_inherited": False,
                "origin_node_id": root_id,
            }
        ],
    )

    node_state = store.get_node_state(project_id, root_id)
    assert node_state["planning"]["turns"] == [
        {
            "turn_id": "turn_2",
            "role": "assistant",
            "content": "Second",
            "timestamp": "2026-03-10T00:01:00Z",
            "is_inherited": False,
            "origin_node_id": root_id,
        }
    ]
    assert node_state["planning"]["event_seq"] >= 1
