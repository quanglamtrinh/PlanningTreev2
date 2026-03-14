from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidWorkspaceRoot, ProjectResetNotAllowed
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    project_service.set_workspace_root(workspace_root)
    return project_service.create_project("Alpha", "Ship phase 3")


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def test_create_project_initializes_root_and_project_files(
    project_service: ProjectService,
    storage: Storage,
    workspace_root: Path,
) -> None:
    project_service.set_workspace_root(str(workspace_root))

    snapshot = project_service.create_project("Alpha", "Ship phase 3")
    project_id = snapshot["project"]["id"]
    root_node = internal_nodes(snapshot)[snapshot["tree_state"]["root_node_id"]]

    assert snapshot["tree_state"]["root_node_id"] == root_node["node_id"]
    assert snapshot["tree_state"]["active_node_id"] == root_node["node_id"]
    assert "title" not in root_node
    assert "description" not in root_node
    assert root_node["status"] == "draft"
    assert root_node["phase"] == "planning"
    assert root_node["node_kind"] == "root"
    assert root_node["hierarchical_number"] == "1"
    assert snapshot["schema_version"] == 5

    assert storage.project_store.meta_path(project_id).exists()
    assert storage.project_store.tree_path(project_id).exists()
    assert storage.project_store.chat_state_path(project_id).exists()
    assert not storage.project_store.tree_path(project_id).with_suffix(".json.tmp").exists()
    assert storage.chat_store.read_chat_state(project_id) == {}
    assert storage.node_store.node_exists(project_id, root_node["node_id"]) is True
    assert storage.node_store.load_task(project_id, root_node["node_id"]) == {
        "title": "Alpha",
        "purpose": "Ship phase 3",
        "responsibility": "",
    }


def test_slug_collision_appends_numeric_suffix(
    project_service: ProjectService,
    workspace_root: Path,
) -> None:
    project_service.set_workspace_root(str(workspace_root))

    first = project_service.create_project("Alpha Build", "First")
    second = project_service.create_project("Alpha Build", "Second")

    assert first["project"]["project_workspace_root"].endswith("alpha-build")
    assert second["project"]["project_workspace_root"].endswith("alpha-build-2")


def test_validate_workspace_root_rejects_non_directory(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "not-a-directory.txt"
    invalid_path.write_text("x", encoding="utf-8")

    with pytest.raises(InvalidWorkspaceRoot):
        project_service.validate_workspace_root(str(invalid_path))


def test_reset_to_root_keeps_root_identity_and_clears_tree_state(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root: Path,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    root_created_at = internal_nodes(snapshot)[root_id]["created_at"]

    first = node_service.create_child(project_id, root_id)
    first_child_id = first["tree_state"]["active_node_id"]
    second = node_service.create_child(project_id, first_child_id)
    grandchild_id = second["tree_state"]["active_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    persisted_root = internal_nodes(persisted)[root_id]
    persisted_root["title"] = "Edited Root"
    persisted_root["description"] = "Edited goal"
    persisted_root["status"] = "in_progress"
    persisted_root["phase"] = "executing"
    persisted_root["node_kind"] = "root"
    persisted_root["planning_mode"] = "slice"
    persisted_root["split_metadata"] = {"mode": "slice"}
    persisted_root["chat_session_id"] = "chat-root"
    persisted_root["planning_thread_id"] = "plan-root"
    persisted_root["execution_thread_id"] = "exec-root"
    persisted_root["planning_thread_forked_from_node"] = first_child_id
    persisted_root["planning_thread_bootstrapped_at"] = "2026-03-09T00:00:00Z"
    storage.project_store.save_snapshot(project_id, persisted)
    storage.node_store.save_task(
        project_id,
        root_id,
        {
            "title": "Edited Root",
            "purpose": "Edited goal",
            "responsibility": "",
        },
    )
    storage.node_store.save_state(
        project_id,
        root_id,
        {
            "phase": "executing",
            "planning_thread_id": "plan-root",
            "execution_thread_id": "exec-root",
            "planning_thread_forked_from_node": first_child_id,
            "planning_thread_bootstrapped_at": "2026-03-09T00:00:00Z",
            "chat_session_id": "chat-root",
        },
    )
    storage.thread_store.write_thread_state(
        project_id,
        {
            root_id: {
                "planning": {
                    "thread_id": "plan-root",
                    "forked_from_node": None,
                    "status": "idle",
                    "active_turn_id": None,
                    "turns": [{"turn_id": "plan-1"}],
                    "event_seq": 1,
                },
                "execution": {
                    "thread_id": "exec-root",
                    "forked_from_planning": True,
                    "status": "idle",
                    "active_turn_id": None,
                    "messages": [{"message_id": "msg-1"}],
                    "event_seq": 1,
                    "config": {"cwd": str(workspace_root)},
                },
            },
            grandchild_id: {
                "planning": {
                    "thread_id": "plan-child",
                    "forked_from_node": first_child_id,
                    "status": "idle",
                    "active_turn_id": None,
                    "turns": [{"turn_id": "plan-2"}],
                    "event_seq": 1,
                },
                "execution": {
                    "thread_id": None,
                    "forked_from_planning": None,
                    "status": None,
                    "active_turn_id": None,
                    "messages": [],
                    "event_seq": 0,
                    "config": None,
                },
            },
        },
    )
    storage.chat_store.write_chat_state(
        project_id,
        {
            root_id: {
                "project_id": project_id,
                "node_id": root_id,
                "thread_id": "exec-root",
                "active_turn_id": None,
                "event_seq": 1,
                "status": "idle",
                "config": {"cwd": str(workspace_root)},
                "messages": [{"message_id": "msg-1"}],
            }
        },
    )

    reset_snapshot = project_service.reset_to_root(project_id)
    root = internal_nodes(reset_snapshot)[root_id]

    assert reset_snapshot["tree_state"]["root_node_id"] == root_id
    assert reset_snapshot["tree_state"]["active_node_id"] == root_id
    assert len(internal_nodes(reset_snapshot)) == 1
    assert root["node_id"] == root_id
    assert "title" not in root
    assert "description" not in root
    assert root["created_at"] == root_created_at
    assert root["status"] == "draft"
    assert root["planning_mode"] is None
    assert root["split_metadata"] is None
    assert root["chat_session_id"] is None
    assert root["parent_id"] is None
    assert root["child_ids"] == []
    assert root["depth"] == 0
    assert root["display_order"] == 0
    assert root["hierarchical_number"] == "1"
    assert root["node_kind"] == "root"
    assert storage.node_store.load_task(project_id, root_id) == {
        "title": "Edited Root",
        "purpose": "Edited goal",
        "responsibility": "",
    }
    assert storage.thread_store.read_thread_state(project_id) == {}
    assert storage.chat_store.read_chat_state(project_id) == {}

    persisted_after = storage.project_store.load_snapshot(project_id)
    persisted_root_after = internal_nodes(persisted_after)[root_id]
    assert persisted_root_after["planning_thread_id"] is None
    assert persisted_root_after["execution_thread_id"] is None
    assert persisted_root_after["planning_thread_forked_from_node"] is None
    assert persisted_root_after["planning_thread_bootstrapped_at"] is None
    assert persisted_root_after["phase"] == "planning"
    assert persisted_root_after["node_kind"] == "root"


def test_reset_to_root_rejects_projects_with_active_turns(
    project_service: ProjectService,
    storage: Storage,
    workspace_root: Path,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    storage.thread_store.write_thread_state(
        project_id,
        {
            root_id: {
                "planning": {
                    "thread_id": "plan-root",
                    "forked_from_node": None,
                    "status": "active",
                    "active_turn_id": "turn-1",
                    "turns": [],
                    "event_seq": 0,
                },
                "execution": {
                    "thread_id": None,
                    "forked_from_planning": None,
                    "status": None,
                    "active_turn_id": None,
                    "messages": [],
                    "event_seq": 0,
                    "config": None,
                },
            }
        },
    )

    with pytest.raises(ProjectResetNotAllowed):
        project_service.reset_to_root(project_id)
