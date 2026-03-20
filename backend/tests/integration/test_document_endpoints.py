from __future__ import annotations

from fastapi.testclient import TestClient


def create_project(client: TestClient, workspace_root: str) -> tuple[str, str]:
    response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": workspace_root},
    )
    assert response.status_code == 200
    snapshot = client.post(
        "/v1/projects",
        json={"name": "Docs Project", "root_goal": "Ship phase 4"},
    ).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def public_node(snapshot: dict, node_id: str) -> dict:
    return next(node for node in snapshot["tree_state"]["node_registry"] if node["node_id"] == node_id)


def test_patch_node_remains_backward_compatible(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.patch(
        f"/v1/projects/{project_id}/nodes/{node_id}",
        json={"title": "Compat Title", "description": "Compat Purpose"},
    )

    assert response.status_code == 200
    node = public_node(response.json(), node_id)
    assert node["title"] == "Compat Title"
    assert node["description"] == "Compat Purpose"

    task = client.app.state.storage.node_store.load_task(project_id, node_id)
    internal = client.app.state.storage.project_store.load_snapshot(project_id)["tree_state"]["node_index"][node_id]
    assert task["title"] == "Compat Title"
    assert task["purpose"] == "Compat Purpose"
    assert "title" not in internal
    assert "description" not in internal
