from __future__ import annotations

from pathlib import Path

from backend.services import planningtree_workspace
from backend.storage.file_utils import atomic_write_json


def test_reset_project_api_rewrites_tree_to_root_only(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    project_dir = workspace_root / ".planningtree"

    created = client.post("/v4/projects/attach", json={"folder_path": str(workspace_root)})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"

    assert root_dir.is_dir()
    assert (root_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (root_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""

    first = client.post(f"/v4/projects/{project_id}/nodes", json={"parent_id": root_id})
    assert first.status_code == 200
    child_dir = root_dir / "1.1 New Node"
    assert child_dir.is_dir()

    reset = client.post(f"/v4/projects/{project_id}/reset-to-root")
    assert reset.status_code == 200
    payload = reset.json()

    assert payload["tree_state"]["root_node_id"] == root_id
    assert payload["tree_state"]["active_node_id"] == root_id
    assert len(payload["tree_state"]["node_registry"]) == 1
    assert root_dir.is_dir()
    assert not child_dir.exists()


def test_snapshot_route_rejects_unsupported_project_layout(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    project_id = "b" * 32
    client.app.state.storage.workspace_store.upsert_entry(project_id, str(workspace_root))
    project_dir = workspace_root / ".planningtree"
    project_dir.mkdir(parents=True)
    atomic_write_json(
        project_dir / "meta.json",
        {
            "id": project_id,
            "name": "Unsupported",
            "root_goal": "Old runtime",
            "created_at": "2026-03-20T00:00:00Z",
            "updated_at": "2026-03-20T00:00:00Z",
        },
    )
    atomic_write_json(
        project_dir / "tree.json",
        {
            "schema_version": 5,
            "project": {"id": project_id},
            "tree_state": {"root_node_id": "root", "active_node_id": "root", "node_index": {}},
            "updated_at": "2026-03-20T00:00:00Z",
        },
    )
    (project_dir / "nodes").mkdir()

    response = client.get(f"/v4/projects/{project_id}/snapshot")

    assert response.status_code == 409
    assert response.json()["code"] == "unsupported_project_layout"
