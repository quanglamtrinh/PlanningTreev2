from __future__ import annotations

from backend.config.app_config import AppPaths
from backend.storage.node_store import NodeStore

PROJECT_ID = "a" * 32


def test_create_and_load(tmp_path) -> None:
    paths = AppPaths(
        data_root=tmp_path,
        projects_root=tmp_path / "projects",
        config_root=tmp_path / "config",
    )
    store = NodeStore(paths)
    (tmp_path / "projects" / PROJECT_ID).mkdir(parents=True)

    store.create_node_files(
        PROJECT_ID,
        "node_001",
        task={"title": "Hello", "purpose": "World", "responsibility": ""},
    )

    assert store.node_exists(PROJECT_ID, "node_001")
    task = store.load_task(PROJECT_ID, "node_001")
    assert task["title"] == "Hello"


def test_save_and_reload(tmp_path) -> None:
    paths = AppPaths(
        data_root=tmp_path,
        projects_root=tmp_path / "projects",
        config_root=tmp_path / "config",
    )
    store = NodeStore(paths)
    (tmp_path / "projects" / PROJECT_ID).mkdir(parents=True)
    store.create_node_files(PROJECT_ID, "node_002")

    store.save_briefing(
        PROJECT_ID,
        "node_002",
        {
            "user_notes": "Important!",
            "business_context": "",
            "technical_context": "",
            "execution_context": "",
            "clarified_answers": "",
        },
    )

    briefing = store.load_briefing(PROJECT_ID, "node_002")
    assert briefing["user_notes"] == "Important!"


def test_delete_node_files(tmp_path) -> None:
    paths = AppPaths(
        data_root=tmp_path,
        projects_root=tmp_path / "projects",
        config_root=tmp_path / "config",
    )
    store = NodeStore(paths)
    (tmp_path / "projects" / PROJECT_ID).mkdir(parents=True)
    store.create_node_files(PROJECT_ID, "node_003")

    assert store.node_exists(PROJECT_ID, "node_003")
    store.delete_node_files(PROJECT_ID, "node_003")
    assert not store.node_exists(PROJECT_ID, "node_003")


def test_node_exists_requires_all_canonical_files(tmp_path) -> None:
    paths = AppPaths(
        data_root=tmp_path,
        projects_root=tmp_path / "projects",
        config_root=tmp_path / "config",
    )
    store = NodeStore(paths)
    node_dir = store.node_dir(PROJECT_ID, "node_004")
    node_dir.mkdir(parents=True)
    (node_dir / "task.md").write_text("# Task\n", encoding="utf-8")

    assert not store.node_exists(PROJECT_ID, "node_004")
