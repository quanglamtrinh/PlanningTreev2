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


def test_document_endpoints_read_and_update_documents(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/documents")

    assert response.status_code == 200
    assert response.json()["task"] == {
        "title": "Docs Project",
        "purpose": "Ship phase 4",
        "responsibility": "",
    }

    task_response = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/task",
        json={"title": "Updated Root"},
    )
    briefing_response = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/briefing",
        json={"business_context": "Business context"},
    )
    spec_response = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/spec",
        json={"technical_contract": "Technical contract"},
    )
    snapshot_response = client.get(f"/v1/projects/{project_id}/snapshot")

    assert task_response.status_code == 200
    assert task_response.json()["task"]["title"] == "Updated Root"
    assert briefing_response.status_code == 200
    assert briefing_response.json()["briefing"]["business_context"] == "Business context"
    assert spec_response.status_code == 200
    assert spec_response.json()["spec"]["technical_contract"] == "Technical contract"
    assert snapshot_response.status_code == 200
    node = public_node(snapshot_response.json(), node_id)
    assert node["title"] == "Updated Root"
    assert node["description"] == "Ship phase 4"

    persisted = client.app.state.storage.project_store.load_snapshot(project_id)
    internal = persisted["tree_state"]["node_index"][node_id]
    assert "title" not in internal
    assert "description" not in internal


def test_spec_endpoint_rejects_executing_phase(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = "executing"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    state = client.app.state.storage.node_store.load_state(project_id, node_id)
    state["phase"] = "executing"
    client.app.state.storage.node_store.save_state(project_id, node_id, state)

    response = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/spec",
        json={"technical_contract": "Frozen"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "node_update_not_allowed"


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
