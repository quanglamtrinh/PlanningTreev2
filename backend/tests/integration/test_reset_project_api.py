from __future__ import annotations

from pathlib import Path

from backend.storage.file_utils import atomic_write_json


def test_reset_project_api_rewrites_tree_to_root_only(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    client.patch("/v1/settings/workspace", json={"base_workspace_root": str(workspace_root)})
    created = client.post(
        "/v1/projects",
        json={"name": "Alpha", "root_goal": "Ship graph-only reset"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]

    first = client.post(f"/v1/projects/{project_id}/nodes", json={"parent_id": root_id})
    assert first.status_code == 200

    reset = client.post(f"/v1/projects/{project_id}/reset-to-root")
    assert reset.status_code == 200
    payload = reset.json()

    assert payload["tree_state"]["root_node_id"] == root_id
    assert payload["tree_state"]["active_node_id"] == root_id
    assert len(payload["tree_state"]["node_registry"]) == 1


def test_snapshot_route_rejects_legacy_project(client, data_root: Path, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    project_id = "b" * 32
    project_dir = data_root / "projects" / project_id
    project_dir.mkdir(parents=True)
    atomic_write_json(
        project_dir / "meta.json",
        {
            "id": project_id,
            "name": "Legacy",
            "root_goal": "Old runtime",
            "base_workspace_root": str(workspace_root),
            "project_workspace_root": str(workspace_root / "legacy"),
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

    response = client.get(f"/v1/projects/{project_id}/snapshot")

    assert response.status_code == 409
    assert response.json()["code"] == "legacy_project_unsupported"
