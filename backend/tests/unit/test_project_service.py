from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidWorkspaceRoot
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    project_service.set_workspace_root(workspace_root)
    return project_service.create_project("Alpha", "Ship graph-only reset")


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def test_create_project_initializes_root_and_minimal_files(
    project_service: ProjectService,
    storage: Storage,
    workspace_root: Path,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    root_node = internal_nodes(snapshot)[root_id]
    project_dir = storage.project_store.project_dir(project_id)

    assert snapshot["schema_version"] == 6
    assert snapshot["tree_state"]["active_node_id"] == root_id
    assert root_node == {
        "node_id": root_id,
        "parent_id": None,
        "child_ids": [],
        "title": "Alpha",
        "description": "Ship graph-only reset",
        "status": "draft",
        "node_kind": "root",
        "depth": 0,
        "display_order": 0,
        "hierarchical_number": "1",
        "created_at": root_node["created_at"],
    }
    assert storage.project_store.meta_path(project_id).exists()
    assert storage.project_store.tree_path(project_id).exists()
    assert not storage.split_state_store.path(project_id).exists()
    assert not (project_dir / "chat_state.json").exists()
    assert not (project_dir / "thread_state.json").exists()
    assert not (project_dir / "nodes").exists()


def test_validate_workspace_root_rejects_non_directory(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "not-a-directory.txt"
    invalid_path.write_text("x", encoding="utf-8")

    with pytest.raises(InvalidWorkspaceRoot):
        project_service.validate_workspace_root(str(invalid_path))


def test_reset_to_root_keeps_root_identity_and_clears_descendants(
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
    node_service.create_child(project_id, first_child_id)

    persisted = storage.project_store.load_snapshot(project_id)
    persisted_root = internal_nodes(persisted)[root_id]
    persisted_root["title"] = "Edited Root"
    persisted_root["description"] = "Edited goal"
    persisted_root["status"] = "in_progress"
    storage.project_store.save_snapshot(project_id, persisted)

    reset_snapshot = project_service.reset_to_root(project_id)
    root = internal_nodes(reset_snapshot)[root_id]

    assert reset_snapshot["tree_state"]["root_node_id"] == root_id
    assert reset_snapshot["tree_state"]["active_node_id"] == root_id
    assert len(internal_nodes(reset_snapshot)) == 1
    assert root["title"] == "Edited Root"
    assert root["description"] == "Edited goal"
    assert root["status"] == "draft"
    assert root["created_at"] == root_created_at
    assert root["child_ids"] == []
