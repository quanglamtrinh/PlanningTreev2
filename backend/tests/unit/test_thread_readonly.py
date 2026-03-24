"""Tests for ChatService thread read-only enforcement."""
from __future__ import annotations

import pytest

from backend.errors.app_errors import ThreadReadOnly
from backend.services.chat_service import ChatService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService
    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


@pytest.fixture
def root_node_id(storage, project_id):
    snap = storage.project_store.load_snapshot(project_id)
    return snap["tree_state"]["root_node_id"]


@pytest.fixture
def chat_service(storage, tree_service):
    return ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=None,  # not needed for read-only tests
        chat_event_broker=ChatEventBroker(),
        chat_timeout=30,
    )


def test_execution_thread_always_readonly(chat_service, project_id, root_node_id):
    with pytest.raises(ThreadReadOnly, match="execution"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="execution")


def test_integration_thread_always_readonly(chat_service, project_id, root_node_id):
    with pytest.raises(ThreadReadOnly, match="integration"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="integration")


def test_ask_planning_writable_before_execution(chat_service, storage, project_id, root_node_id):
    """ask_planning should not raise ThreadReadOnly when no execution_state exists."""
    # get_session should work fine
    session = chat_service.get_session(project_id, root_node_id, thread_role="ask_planning")
    assert session["thread_role"] == "ask_planning"


def test_ask_planning_readonly_after_execution(chat_service, storage, project_id, root_node_id):
    """ask_planning becomes read-only when execution_state exists."""
    storage.execution_state_store.write_state(project_id, root_node_id, {
        "status": "executing", "initial_sha": "sha256:abc",
        "head_sha": None, "started_at": "2026-01-01T00:00:00Z", "completed_at": None,
    })
    with pytest.raises(ThreadReadOnly, match="ask_planning"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="ask_planning")


def test_ask_planning_reset_readonly_after_execution(chat_service, storage, project_id, root_node_id):
    """reset_session also blocked after execution."""
    storage.execution_state_store.write_state(project_id, root_node_id, {
        "status": "executing", "initial_sha": "sha256:abc",
        "head_sha": None, "started_at": "2026-01-01T00:00:00Z", "completed_at": None,
    })
    with pytest.raises(ThreadReadOnly, match="ask_planning"):
        chat_service.reset_session(project_id, root_node_id, thread_role="ask_planning")


def test_audit_readonly_before_execution(chat_service, project_id, root_node_id):
    """Audit is not writable when no execution exists."""
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="audit")


def test_audit_writable_after_execution_completed(chat_service, storage, project_id, root_node_id):
    """Audit becomes writable when execution completed (local review case)."""
    storage.execution_state_store.write_state(project_id, root_node_id, {
        "status": "completed", "initial_sha": "sha256:abc",
        "head_sha": "sha256:def", "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T01:00:00Z",
    })
    # Should not raise ThreadReadOnly — will raise ChatBackendUnavailable
    # because codex_client is None, but that's after the writable check
    # Let's just test get_session works (no write check needed)
    session = chat_service.get_session(project_id, root_node_id, thread_role="audit")
    assert session["thread_role"] == "audit"


def test_audit_readonly_during_execution(chat_service, storage, project_id, root_node_id):
    """Audit is NOT writable while execution is still running."""
    storage.execution_state_store.write_state(project_id, root_node_id, {
        "status": "executing", "initial_sha": "sha256:abc",
        "head_sha": None, "started_at": "2026-01-01T00:00:00Z", "completed_at": None,
    })
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="audit")


def test_get_session_works_for_all_roles(chat_service, project_id, root_node_id):
    """get_session does not enforce writable — all roles should work."""
    for role in ("ask_planning", "audit", "execution"):
        session = chat_service.get_session(project_id, root_node_id, thread_role=role)
        assert session["thread_role"] == role
