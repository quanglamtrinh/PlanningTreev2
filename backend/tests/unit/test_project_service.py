from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidProjectFolder
from backend.services import planningtree_workspace
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.storage.project_store import CURRENT_SCHEMA_VERSION
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


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
        "title": "workspace",
        "description": "",
        "status": "draft",
        "node_kind": "root",
        "depth": 0,
        "display_order": 0,
        "hierarchical_number": "1",
        "created_at": root_node["created_at"],
        "review_node_id": None,
    }
    assert storage.project_store.meta_path(project_id).exists()
    assert storage.project_store.tree_path(project_id).exists()
    assert not storage.workflow_domain_store.artifact_jobs_path(project_id).exists()
    assert snapshot["project"]["project_path"] == str(workspace_root.resolve())
    assert not (project_dir / "chat").exists()
    assert not (project_dir / "state.json").exists()
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    assert root_dir.is_dir()
    assert (root_dir / planningtree_workspace.NODE_MARKER_NAME).read_text(encoding="utf-8").strip() == root_id
    assert (root_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (root_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""
    assert json.loads((root_dir / planningtree_workspace.SPEC_META_FILE_NAME).read_text(encoding="utf-8")) == {
        "source_frame_revision": 0,
        "confirmed_at": None,
    }


def test_validate_project_folder_rejects_non_directory(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "not-a-directory.txt"
    invalid_path.write_text("x", encoding="utf-8")

    with pytest.raises(InvalidProjectFolder):
        project_service.validate_project_folder(str(invalid_path))


def test_delete_project_detaches_without_deleting_local_data(
    project_service: ProjectService,
    storage: Storage,
    workspace_root: Path,
) -> None:
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    project_dir = storage.project_store.project_dir(project_id)

    assert project_dir.exists()

    project_service.delete_project(project_id)

    assert project_dir.exists()
    assert storage.workspace_store.list_entries() == []
    assert (project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace").is_dir()


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
    root_dir = storage.project_store.project_dir(project_id) / planningtree_workspace.ROOT_SEGMENT / "1 Edited Root"

    assert reset_snapshot["tree_state"]["root_node_id"] == root_id
    assert reset_snapshot["tree_state"]["active_node_id"] == root_id
    assert len(internal_nodes(reset_snapshot)) == 1
    assert root["title"] == "Edited Root"
    assert root["description"] == "Edited goal"
    assert root["status"] == "draft"
    assert root["created_at"] == root_created_at
    assert root["child_ids"] == []
    assert root_dir.is_dir()
    assert (root_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (root_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""
    assert sorted(path.name for path in root_dir.iterdir()) == sorted(
        [
            planningtree_workspace.NODE_MARKER_NAME,
            planningtree_workspace.FRAME_FILE_NAME,
            planningtree_workspace.SPEC_FILE_NAME,
            planningtree_workspace.FRAME_META_FILE_NAME,
            planningtree_workspace.SPEC_META_FILE_NAME,
        ]
    )


def test_attach_existing_project_backfills_node_folder_projection(
    project_service: ProjectService,
    storage: Storage,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "existing-workspace"
    workspace_root.mkdir()
    project_id = "1234567890abcdef1234567890abcdef"
    root_id = "abcdefabcdefabcdefabcdefabcdefab"
    child_id = "fedcbafedcbafedcbafedcbafedcbafe"
    snapshot = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project": {
            "id": project_id,
            "name": "existing-workspace",
            "root_goal": "existing-workspace",
            "created_at": "2026-03-21T10:00:00Z",
            "updated_at": "2026-03-21T10:00:00Z",
        },
        "tree_state": {
            "root_node_id": root_id,
            "active_node_id": child_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [child_id],
                    "title": "existing-workspace",
                    "description": "",
                    "status": "draft",
                    "node_kind": "root",
                    "depth": 0,
                    "display_order": 0,
                    "hierarchical_number": "1",
                    "created_at": "2026-03-21T10:00:00Z",
                },
                child_id: {
                    "node_id": child_id,
                    "parent_id": root_id,
                    "child_ids": [],
                    "title": "child node",
                    "description": "",
                    "status": "ready",
                    "node_kind": "original",
                    "depth": 1,
                    "display_order": 0,
                    "hierarchical_number": "1.1",
                    "created_at": "2026-03-21T10:00:00Z",
                },
            },
        },
        "updated_at": "2026-03-21T10:00:00Z",
    }
    storage.project_store.create_project_files(str(workspace_root), snapshot["project"], snapshot)

    attached = project_service.attach_project_folder(str(workspace_root))
    attached_id = attached["project"]["id"]
    project_dir = storage.project_store.project_dir(attached_id)
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 existing-workspace"
    child_dir = root_dir / "1.1 child node"

    assert attached_id == project_id
    assert root_dir.is_dir()
    assert child_dir.is_dir()
    assert (root_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (child_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""


def test_bootstrap_status_exposes_core_readiness_only(storage: Storage) -> None:
    service = ProjectService(storage)

    status = service.bootstrap_status()

    assert status["ready"] is True
    assert status["workspace_configured"] is True
    assert status["ask_followup_queue_enabled"] is False
    assert "execution_audit_v2_enabled" not in status
    assert "execution_audit_uiux_v3_backend_enabled" not in status
    assert "execution_audit_uiux_v3_frontend_enabled" not in status
    assert "execution_uiux_v3_frontend_enabled" not in status
    assert "audit_uiux_v3_frontend_enabled" not in status
