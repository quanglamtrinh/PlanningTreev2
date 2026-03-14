from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.main import create_app
from backend.storage.file_utils import iso_now


def test_codex_transport_error_returns_structured_502(data_root: Path, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    app = create_app(data_root=data_root)
    project_id = "a" * 32
    node_id = "b" * 32
    now = iso_now()
    snapshot = {
        "schema_version": 5,
        "project": {
            "id": project_id,
            "name": "Alpha",
            "root_goal": "Ship phase 4",
            "base_workspace_root": str(workspace_root),
            "project_workspace_root": str(workspace_root),
            "created_at": now,
            "updated_at": now,
        },
        "tree_state": {
            "root_node_id": node_id,
            "active_node_id": node_id,
            "node_index": {
                node_id: {
                    "node_id": node_id,
                    "parent_id": None,
                    "child_ids": [],
                    "status": "draft",
                    "phase": "ready_for_execution",
                    "node_kind": "root",
                    "planning_mode": None,
                    "depth": 0,
                    "display_order": 0,
                    "hierarchical_number": "1",
                    "split_metadata": None,
                    "chat_session_id": None,
                    "planning_thread_id": None,
                    "execution_thread_id": None,
                    "planning_thread_forked_from_node": None,
                    "planning_thread_bootstrapped_at": None,
                    "created_at": now,
                }
            },
        },
        "updated_at": now,
    }
    app.state.storage.project_store.create_project_files(snapshot["project"], snapshot)
    app.state.storage.node_store.create_node_files(
        project_id,
        node_id,
        task={"title": "Alpha", "purpose": "Ship phase 4", "responsibility": ""},
        state={"phase": "ready_for_execution"},
    )

    def raise_transport_error(project_id: str, node_id: str) -> None:
        raise CodexTransportError("boom", "rpc_error")

    app.state.thread_service.create_execution_thread = raise_transport_error

    with TestClient(app) as client:
        response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/start-execution")

    assert response.status_code == 502
    assert response.json() == {
        "code": "rpc_error",
        "message": "boom",
    }
