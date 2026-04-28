from __future__ import annotations

import pytest

from backend.errors.app_errors import InvalidRequest, NodeCreateNotAllowed
from backend.services import planningtree_workspace
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def test_create_child_selects_new_node_and_locks_follow_on_siblings(
    project_service: ProjectService,
    node_service: NodeService,
    storage,
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
    project_dir = storage.project_store.project_dir(project_id)
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    first_dir = root_dir / "1.1 New Node"
    second_dir = root_dir / "1.2 New Node"
    assert first_dir.is_dir()
    assert second_dir.is_dir()
    assert (first_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (second_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""


def test_update_node_changes_inline_title_and_description(
    project_service: ProjectService,
    node_service: NodeService,
    storage,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    project_dir = storage.project_store.project_dir(project_id)
    original_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    (original_dir / planningtree_workspace.FRAME_FILE_NAME).write_text("keep me", encoding="utf-8")

    updated = node_service.update_node(
        project_id,
        root_id,
        title="Renamed Root",
        description="New description",
    )
    node = internal_nodes(updated)[root_id]

    assert node["title"] == "Renamed Root"
    assert node["description"] == "New description"
    renamed_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 Renamed Root"
    assert renamed_dir.is_dir()
    assert not original_dir.exists()
    assert (renamed_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == "keep me"


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


def test_create_task_from_init_node_uses_description_and_keeps_locking_rules(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    first = node_service.create_task(project_id, root_id, "Build task breakdown from prompt")
    second = node_service.create_task(project_id, root_id, "Prepare rollout checklist")

    first_task_id = first["tree_state"]["active_node_id"]
    second_task_id = second["tree_state"]["active_node_id"]
    nodes = internal_nodes(second)

    assert first_task_id != second_task_id
    assert nodes[first_task_id]["title"] == "Build task breakdown from prompt"
    assert nodes[first_task_id]["description"] == "Build task breakdown from prompt"
    assert nodes[first_task_id]["status"] == "ready"
    assert nodes[second_task_id]["title"] == "Prepare rollout checklist"
    assert nodes[second_task_id]["description"] == "Prepare rollout checklist"
    assert nodes[second_task_id]["status"] == "locked"


def test_create_task_rejects_non_init_parent(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    first = node_service.create_child(project_id, root_id)
    child_id = first["tree_state"]["active_node_id"]

    with pytest.raises(NodeCreateNotAllowed):
        node_service.create_task(project_id, child_id, "Should fail")
