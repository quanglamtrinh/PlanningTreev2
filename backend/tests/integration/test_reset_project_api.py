from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.storage.file_utils import iso_now


def make_snapshot(project_id: str, root_id: str, child_id: str, workspace_root: Path) -> dict:
    now = iso_now()
    return {
        "schema_version": 4,
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
            "root_node_id": root_id,
            "active_node_id": child_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [child_id],
                    "title": "Renamed Root",
                    "description": "Current root text",
                    "status": "in_progress",
                    "phase": "executing",
                    "planning_mode": "slice",
                    "depth": 0,
                    "display_order": 0,
                    "hierarchical_number": "1",
                    "node_kind": "root",
                    "split_metadata": {"mode": "slice"},
                    "chat_session_id": "chat-root",
                    "planning_thread_id": "plan-root",
                    "execution_thread_id": "exec-root",
                    "planning_thread_forked_from_node": None,
                    "planning_thread_bootstrapped_at": now,
                    "created_at": now,
                },
                child_id: {
                    "node_id": child_id,
                    "parent_id": root_id,
                    "child_ids": [],
                    "title": "Child",
                    "description": "Child node",
                    "status": "ready",
                    "phase": "planning",
                    "planning_mode": None,
                    "depth": 1,
                    "display_order": 0,
                    "hierarchical_number": "1.1",
                    "node_kind": "original",
                    "split_metadata": None,
                    "chat_session_id": None,
                    "planning_thread_id": None,
                    "execution_thread_id": None,
                    "planning_thread_forked_from_node": None,
                    "planning_thread_bootstrapped_at": None,
                    "created_at": now,
                },
            },
        },
        "updated_at": now,
    }


def test_reset_project_api_rewrites_tree_to_root_only(data_root: Path, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    app = create_app(data_root=data_root)
    project_id = "a" * 32
    root_id = "b" * 32
    child_id = "c" * 32
    snapshot = make_snapshot(project_id, root_id, child_id, workspace_root)
    app.state.storage.project_store.create_project_files(snapshot["project"], snapshot)
    app.state.storage.node_store.create_node_files(
        project_id,
        root_id,
        task={"title": "Renamed Root", "purpose": "Current root text", "responsibility": ""},
        state={
            "phase": "executing",
            "planning_thread_id": "plan-root",
            "execution_thread_id": "exec-root",
            "planning_thread_bootstrapped_at": snapshot["tree_state"]["node_index"][root_id]["planning_thread_bootstrapped_at"],
            "chat_session_id": "chat-root",
        },
    )
    app.state.storage.node_store.create_node_files(
        project_id,
        child_id,
        task={"title": "Child", "purpose": "Child node", "responsibility": ""},
    )
    app.state.storage.thread_store.write_thread_state(
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
            }
        },
    )
    app.state.storage.chat_store.write_chat_state(
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

    def bootstrap_root(project_id_arg: str) -> dict:
        persisted = app.state.storage.project_store.load_snapshot(project_id_arg)
        root = persisted["tree_state"]["node_index"][root_id]
        root["planning_thread_id"] = "plan-reset"
        app.state.storage.project_store.save_snapshot(project_id_arg, persisted)
        state = app.state.storage.node_store.load_state(project_id_arg, root_id)
        state["planning_thread_id"] = "plan-reset"
        app.state.storage.node_store.save_state(project_id_arg, root_id, state)
        app.state.storage.thread_store.write_thread_state(
            project_id_arg,
            {
                root_id: {
                    "planning": {
                        "thread_id": "plan-reset",
                        "forked_from_node": None,
                        "status": "idle",
                        "active_turn_id": None,
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
        return persisted

    app.state.thread_service.initialize_root_planning_thread = bootstrap_root

    with TestClient(app) as client:
        response = client.post(f"/v1/projects/{project_id}/reset-to-root")
        reloaded = client.get(f"/v1/projects/{project_id}/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tree_state"]["root_node_id"] == root_id
    assert payload["tree_state"]["active_node_id"] == root_id
    assert len(payload["tree_state"]["node_registry"]) == 1
    root = payload["tree_state"]["node_registry"][0]
    assert root["node_id"] == root_id
    assert root["title"] == "Renamed Root"
    assert root["description"] == "Current root text"
    assert root["status"] == "draft"
    assert root["planning_mode"] is None
    assert root["split_metadata"] is None
    assert root["has_planning_thread"] is True
    assert app.state.storage.chat_store.read_chat_state(project_id) == {}
    assert root_id in app.state.storage.thread_store.read_thread_state(project_id)
    assert reloaded.status_code == 200
    assert reloaded.json()["tree_state"] == payload["tree_state"]


def test_reset_project_api_allows_reset_after_stale_turn_reconciliation(data_root: Path, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    app = create_app(data_root=data_root)
    project_id = "d" * 32
    root_id = "e" * 32
    child_id = "f" * 32
    snapshot = make_snapshot(project_id, root_id, child_id, workspace_root)
    app.state.storage.project_store.create_project_files(snapshot["project"], snapshot)
    app.state.storage.node_store.create_node_files(
        project_id,
        root_id,
        task={"title": "Renamed Root", "purpose": "Current root text", "responsibility": ""},
        state={
            "phase": "executing",
            "planning_thread_id": "plan-root",
            "execution_thread_id": "exec-root",
            "planning_thread_bootstrapped_at": snapshot["tree_state"]["node_index"][root_id]["planning_thread_bootstrapped_at"],
            "chat_session_id": "chat-root",
        },
    )
    app.state.storage.node_store.create_node_files(
        project_id,
        child_id,
        task={"title": "Child", "purpose": "Child node", "responsibility": ""},
    )
    app.state.storage.thread_store.write_thread_state(
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

    with TestClient(app) as client:
        response = client.post(f"/v1/projects/{project_id}/reset-to-root")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tree_state"]["root_node_id"] == root_id
    assert payload["tree_state"]["active_node_id"] == root_id
    assert len(payload["tree_state"]["node_registry"]) == 1
