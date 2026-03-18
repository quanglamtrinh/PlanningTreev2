from __future__ import annotations

from pathlib import Path

import pytest

from backend.storage.file_utils import atomic_write_json, iso_now
from backend.storage.storage import Storage


def _v3_snapshot(project_id: str) -> dict:
    return {
        "schema_version": 3,
        "project": {
            "id": project_id,
            "name": "Test",
            "root_goal": "Ship phase 4",
            "base_workspace_root": "C:/workspace",
            "project_workspace_root": "C:/workspace/test",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        },
        "tree_state": {
            "root_node_id": "root_001",
            "active_node_id": "child_001",
            "node_registry": [
                {
                    "node_id": "root_001",
                    "parent_id": None,
                    "child_ids": ["child_001"],
                    "title": "Root Task",
                    "description": "Build something",
                    "status": "draft",
                    "planning_mode": "walking_skeleton",
                    "depth": 0,
                    "display_order": 0,
                    "hierarchical_number": "1",
                    "split_metadata": None,
                    "chat_session_id": None,
                    "planning_thread_id": "thread_abc",
                    "execution_thread_id": None,
                    "planning_thread_forked_from_node": None,
                    "planning_thread_bootstrapped_at": None,
                    "is_superseded": False,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "node_id": "child_001",
                    "parent_id": "root_001",
                    "child_ids": [],
                    "title": "Child Task",
                    "description": "Do subthing",
                    "status": "ready",
                    "planning_mode": None,
                    "depth": 1,
                    "display_order": 0,
                    "hierarchical_number": "1.1",
                    "split_metadata": None,
                    "chat_session_id": "chat_xyz",
                    "planning_thread_id": "thread_def",
                    "execution_thread_id": "thread_ghi",
                    "planning_thread_forked_from_node": "root_001",
                    "planning_thread_bootstrapped_at": "2026-01-02T00:00:00Z",
                    "is_superseded": False,
                    "created_at": "2026-01-02T00:00:00Z",
                },
            ],
        },
        "updated_at": "2026-01-02T00:00:00Z",
    }


def _write_v3_project(storage: Storage, project_id: str) -> Path:
    snapshot = _v3_snapshot(project_id)
    project_dir = storage.project_store.project_dir(project_id)
    project_dir.mkdir(parents=True)
    atomic_write_json(project_dir / "state.json", snapshot)
    atomic_write_json(project_dir / "meta.json", snapshot["project"])
    atomic_write_json(project_dir / "thread_state.json", {})
    atomic_write_json(project_dir / "chat_state.json", {})
    return project_dir


def _write_v4_project(storage: Storage, project_id: str, root_id: str) -> None:
    now = iso_now()
    snapshot = {
        "schema_version": 4,
        "project": {
            "id": project_id,
            "name": "Alpha",
            "root_goal": "Ship phase 4",
            "base_workspace_root": "C:/workspace",
            "project_workspace_root": "C:/workspace/alpha",
            "created_at": now,
            "updated_at": now,
        },
        "tree_state": {
            "root_node_id": root_id,
            "active_node_id": root_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [],
                    "title": "Alpha",
                    "description": "Ship phase 4",
                    "status": "draft",
                    "phase": "planning",
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
    project_dir = storage.project_store.project_dir(project_id)
    project_dir.mkdir(parents=True)
    atomic_write_json(project_dir / "meta.json", snapshot["project"])
    atomic_write_json(project_dir / "tree.json", snapshot)
    atomic_write_json(project_dir / "thread_state.json", {})
    atomic_write_json(project_dir / "chat_state.json", {})
    storage.node_store.create_node_files(
        project_id,
        root_id,
        task={"title": "Alpha", "purpose": "Ship phase 4", "responsibility": ""},
    )


def test_v3_to_v5_migration_creates_tree_json_and_node_files(storage: Storage) -> None:
    project_id = "a" * 32
    project_dir = _write_v3_project(storage, project_id)

    tree = storage.project_store.load_snapshot(project_id)

    assert tree["schema_version"] == 5
    assert "node_index" in tree["tree_state"]
    assert "node_registry" not in tree["tree_state"]
    assert "root_001" in tree["tree_state"]["node_index"]
    assert "child_001" in tree["tree_state"]["node_index"]
    assert tree["tree_state"]["node_index"]["root_001"]["node_kind"] == "root"
    assert tree["tree_state"]["node_index"]["child_001"]["node_kind"] == "original"
    assert tree["tree_state"]["node_index"]["root_001"]["planning_mode"] is None
    assert "title" not in tree["tree_state"]["node_index"]["root_001"]
    assert "description" not in tree["tree_state"]["node_index"]["root_001"]
    assert tree["tree_state"]["node_index"]["root_001"]["planning_thread_id"] == "thread_abc"
    assert tree["tree_state"]["node_index"]["child_001"]["execution_thread_id"] == "thread_ghi"
    assert storage.project_store.tree_path(project_id).exists()
    assert (project_dir / "state.json.bak").exists()
    assert not (project_dir / "state.json").exists()
    assert storage.node_store.node_exists(project_id, "root_001")
    assert storage.node_store.node_exists(project_id, "child_001")

    root_task = storage.node_store.load_task(project_id, "root_001")
    assert root_task["title"] == "Root Task"
    assert root_task["purpose"] == "Build something"

    child_task = storage.node_store.load_task(project_id, "child_001")
    assert child_task["title"] == "Child Task"
    assert child_task["purpose"] == "Do subthing"

    root_state = storage.node_store.load_state(project_id, "root_001")
    assert root_state["phase"] == "planning"
    assert root_state["planning_thread_id"] == "thread_abc"

    child_state = storage.node_store.load_state(project_id, "child_001")
    assert child_state["phase"] == "planning"
    assert child_state["planning_thread_id"] == "thread_def"
    assert child_state["execution_thread_id"] == "thread_ghi"
    assert child_state["planning_thread_forked_from_node"] == "root_001"
    assert child_state["chat_session_id"] == "chat_xyz"


def test_v4_tree_migrates_to_v5_on_load(storage: Storage) -> None:
    project_id = "b" * 32
    root_id = "root_v4"
    _write_v4_project(storage, project_id, root_id)

    tree = storage.project_store.load_snapshot(project_id)

    assert tree["schema_version"] == 5
    assert tree["tree_state"]["root_node_id"] == root_id
    assert "title" not in tree["tree_state"]["node_index"][root_id]
    assert "description" not in tree["tree_state"]["node_index"][root_id]
    assert storage.node_store.load_task(project_id, root_id)["title"] == "Alpha"
    assert storage.project_store.tree_path(project_id).exists()
    assert not storage.project_store.state_path(project_id).exists()


def test_migration_is_idempotent(storage: Storage) -> None:
    project_id = "c" * 32
    _write_v3_project(storage, project_id)

    first = storage.project_store.load_snapshot(project_id)
    second = storage.project_store.load_snapshot(project_id)

    assert first == second
    assert storage.project_store.tree_path(project_id).exists()
    assert not storage.project_store.state_path(project_id).exists()
    assert storage.project_store.project_dir(project_id).joinpath("state.json.bak").exists()


def test_migration_resumes_when_complete_node_dir_already_exists(storage: Storage) -> None:
    project_id = "e" * 32
    _write_v3_project(storage, project_id)
    storage.node_store.create_node_files(
        project_id,
        "root_001",
        task={"title": "Root Task", "purpose": "Build something", "responsibility": ""},
        state={
            "phase": "planning",
            "planning_thread_id": "thread_abc",
        },
    )

    tree = storage.project_store.load_snapshot(project_id)

    assert tree["schema_version"] == 5
    assert storage.node_store.node_exists(project_id, "root_001")
    assert storage.node_store.node_exists(project_id, "child_001")
    assert storage.node_store.load_task(project_id, "root_001")["title"] == "Root Task"
    assert "title" not in tree["tree_state"]["node_index"]["root_001"]


def test_migration_recreates_incomplete_existing_node_dir(storage: Storage) -> None:
    project_id = "f" * 32
    _write_v3_project(storage, project_id)
    partial_dir = storage.node_store.node_dir(project_id, "root_001")
    partial_dir.mkdir(parents=True)
    (partial_dir / "task.md").write_text("# Partial\n", encoding="utf-8")

    tree = storage.project_store.load_snapshot(project_id)

    assert tree["schema_version"] == 5
    assert storage.node_store.node_exists(project_id, "root_001")
    assert storage.node_store.load_task(project_id, "root_001") == {
        "title": "Root Task",
        "purpose": "Build something",
        "responsibility": "",
    }
    assert "title" not in tree["tree_state"]["node_index"]["root_001"]


def test_v4_tree_missing_node_files_fails_fast(storage: Storage) -> None:
    project_id = "d" * 32
    root_id = "root_missing"
    _write_v4_project(storage, project_id, root_id)
    storage.node_store.delete_node_files(project_id, root_id)

    with pytest.raises(ValueError, match="missing or incomplete node files"):
        storage.project_store.load_snapshot(project_id)
