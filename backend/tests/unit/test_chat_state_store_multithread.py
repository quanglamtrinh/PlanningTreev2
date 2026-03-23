from __future__ import annotations

import json

import pytest

from backend.storage.storage import Storage


@pytest.fixture
def chat_store(storage):
    return storage.chat_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService

    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


def test_read_session_default_thread_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1")
    assert session["thread_role"] == "ask_planning"


def test_read_session_with_explicit_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    assert session["thread_role"] == "audit"


def test_write_and_read_with_thread_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    session["thread_id"] = "thread-audit-1"
    chat_store.write_session(project_id, "node1", session, thread_role="audit")

    loaded = chat_store.read_session(project_id, "node1", thread_role="audit")
    assert loaded["thread_id"] == "thread-audit-1"
    assert loaded["thread_role"] == "audit"

    # ask_planning session should be separate
    ask = chat_store.read_session(project_id, "node1", thread_role="ask_planning")
    assert ask["thread_id"] is None
    assert ask["thread_role"] == "ask_planning"


def test_separate_sessions_per_role(chat_store, project_id):
    for role in ("ask_planning", "audit", "execution"):
        session = chat_store.read_session(project_id, "node1", thread_role=role)
        session["thread_id"] = f"thread-{role}"
        chat_store.write_session(project_id, "node1", session, thread_role=role)

    for role in ("ask_planning", "audit", "execution"):
        loaded = chat_store.read_session(project_id, "node1", thread_role=role)
        assert loaded["thread_id"] == f"thread-{role}"
        assert loaded["thread_role"] == role


def test_clear_session_with_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    session["thread_id"] = "t1"
    chat_store.write_session(project_id, "node1", session, thread_role="audit")

    cleared = chat_store.clear_session(project_id, "node1", thread_role="audit")
    assert cleared["thread_id"] is None
    assert cleared["thread_role"] == "audit"


def test_invalid_thread_role_falls_back_to_default(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="invalid_role")
    assert session["thread_role"] == "ask_planning"


def test_flat_file_migration(chat_store, project_id):
    """Old flat chat/{node_id}.json should be migrated to chat/{node_id}/ask_planning.json."""
    flat_path = chat_store._flat_path(project_id, "migrate_node")
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    flat_data = {
        "thread_id": "old-thread",
        "active_turn_id": None,
        "messages": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    flat_path.write_text(json.dumps(flat_data), encoding="utf-8")
    assert flat_path.exists()

    # Reading should trigger migration
    session = chat_store.read_session(project_id, "migrate_node")
    assert session["thread_id"] == "old-thread"
    assert session["thread_role"] == "ask_planning"

    # Flat file should be gone, directory should exist
    assert not flat_path.exists()
    role_dir = chat_store._role_dir(project_id, "migrate_node")
    assert role_dir.exists()
    assert (role_dir / "ask_planning.json").exists()


def test_migration_skipped_if_directory_exists(chat_store, project_id):
    """If directory already exists, don't migrate even if flat file exists."""
    flat_path = chat_store._flat_path(project_id, "node2")
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    flat_data = {"thread_id": "old", "active_turn_id": None, "messages": [],
                 "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    flat_path.write_text(json.dumps(flat_data), encoding="utf-8")

    # Create the directory first
    role_dir = chat_store._role_dir(project_id, "node2")
    role_dir.mkdir(parents=True, exist_ok=True)

    session = chat_store.read_session(project_id, "node2")
    # Should return default (no migrated data) since directory exists but no ask_planning.json
    assert session["thread_id"] is None

    # Flat file should still exist (wasn't migrated)
    assert flat_path.exists()


def test_role_path_structure(chat_store, project_id):
    path = chat_store.path(project_id, "node1", "audit")
    assert path.name == "audit.json"
    assert path.parent.name == "node1"
