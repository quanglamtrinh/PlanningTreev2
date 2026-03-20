from __future__ import annotations

import pytest

from backend.errors.app_errors import InvalidRequest, NodeCreateNotAllowed
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    project_service.set_workspace_root(workspace_root)
    return project_service.create_project("Alpha", "Ship graph-only reset")


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def test_create_child_selects_new_node_and_locks_follow_on_siblings(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    first = node_service.create_child(project_id, root_id)
    second = node_service.create_child(project_id, root_id)

    first_child_id = first["tree_state"]["active_node_id"]
    second_child_id = second["tree_state"]["active_node_id"]
    nodes = internal_nodes(second)

    assert first_child_id != second_child_id
    assert second["tree_state"]["active_node_id"] == second_child_id
    assert nodes[first_child_id]["status"] == "ready"
    assert nodes[second_child_id]["status"] == "locked"


def test_update_node_changes_inline_title_and_description(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    updated = node_service.update_node(
        project_id,
        root_id,
        title="Renamed Root",
        description="New description",
    )
    node = internal_nodes(updated)[root_id]

    assert node["title"] == "Renamed Root"
    assert node["description"] == "New description"


def test_update_node_rejects_blank_title(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    with pytest.raises(InvalidRequest):
        node_service.update_node(project_id, root_id, title="   ")


def test_create_child_under_done_node_is_blocked(
    project_service: ProjectService,
    node_service: NodeService,
    storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    persisted = storage.project_store.load_snapshot(project_id)
    persisted["tree_state"]["node_index"][root_id]["status"] = "done"
    storage.project_store.save_snapshot(project_id, persisted)

    with pytest.raises(NodeCreateNotAllowed):
        node_service.create_child(project_id, root_id)
