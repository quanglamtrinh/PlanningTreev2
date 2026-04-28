from __future__ import annotations

import pytest

from backend.config.app_config import build_app_paths
from backend.storage.chat_state_store import ChatStateStore
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.storage import Storage


@pytest.fixture
def chat_store(data_root, storage):
    return storage.chat_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService

    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


def test_read_returns_default_when_no_file(chat_store, project_id):
    session = chat_store.read_session(project_id, "nonexistent_node")
    assert session["thread_id"] is None
    assert session["active_turn_id"] is None
    assert session["messages"] == []
    assert isinstance(session["created_at"], str)
    assert isinstance(session["updated_at"], str)


def test_write_and_read_round_trip(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1")
    session["thread_id"] = "thread-abc"
    session["messages"].append({
        "message_id": "msg-1",
        "role": "user",
        "content": "Hello",
        "status": "completed",
        "error": None,
        "turn_id": "turn-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    chat_store.write_session(project_id, "node1", session)

    loaded = chat_store.read_session(project_id, "node1")
    assert loaded["thread_id"] == "thread-abc"
    assert len(loaded["messages"]) == 1
    assert loaded["messages"][0]["content"] == "Hello"
    assert loaded["messages"][0]["role"] == "user"


def test_root_thread_role_writes_root_session_file(chat_store, project_id):
    session = chat_store.read_session(project_id, "root-node", thread_role="root")
    session["thread_id"] = "root-thread-1"

    saved = chat_store.write_session(project_id, "root-node", session, thread_role="root")
    loaded = chat_store.read_session(project_id, "root-node", thread_role="root")

    assert saved["thread_role"] == "root"
    assert loaded["thread_id"] == "root-thread-1"
    assert chat_store.path(project_id, "root-node", thread_role="root").name == "root.json"


def test_clear_session_restores_default(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1")
    session["thread_id"] = "thread-abc"
    session["messages"].append({
        "message_id": "msg-1",
        "role": "user",
        "content": "Hello",
        "status": "completed",
        "error": None,
        "turn_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    chat_store.write_session(project_id, "node1", session)

    cleared = chat_store.clear_session(project_id, "node1")
    assert cleared["thread_id"] is None
    assert cleared["messages"] == []


def test_clear_all_sessions_removes_chat_directory(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1")
    session["thread_id"] = "t1"
    chat_store.write_session(project_id, "node1", session)
    chat_store.write_session(project_id, "node2", session)

    chat_dir = chat_store._chat_dir(project_id)
    assert chat_dir.exists()

    chat_store.clear_all_sessions(project_id)
    assert not chat_dir.exists()


def test_normalize_handles_corrupt_payload(chat_store):
    result = chat_store._normalize_session("not a dict")
    assert result["thread_id"] is None
    assert result["messages"] == []


def test_normalize_handles_corrupt_messages(chat_store):
    result = chat_store._normalize_session({
        "messages": [
            "not a dict",
            {"message_id": "m1"},  # missing role
            {"message_id": "m2", "role": "user", "content": "ok", "status": "completed"},
        ],
    })
    assert len(result["messages"]) == 1
    assert result["messages"][0]["message_id"] == "m2"


def test_normalize_message_defaults(chat_store):
    msg = chat_store._normalize_message({
        "message_id": "m1",
        "role": "assistant",
    })
    assert msg is not None
    assert msg["content"] == ""
    assert msg["status"] == "pending"
    assert msg["error"] is None
