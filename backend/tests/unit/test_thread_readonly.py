"""Tests for ChatService thread read-only enforcement."""
from __future__ import annotations

import pytest

from backend.errors.app_errors import ThreadReadOnly
from backend.services.chat_service import ChatService
from backend.services.execution_gating import AUDIT_ROLLUP_PACKAGE_MESSAGE_ID
from backend.services.project_service import ProjectService
from backend.streaming.sse_broker import ChatEventBroker


@pytest.fixture
def project_id(storage, workspace_root):
    snap = ProjectService(storage).attach_project_folder(str(workspace_root))
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
        codex_client=None,
        chat_event_broker=ChatEventBroker(),
        chat_timeout=30,
    )


def test_execution_thread_always_readonly(chat_service, project_id, root_node_id):
    with pytest.raises(ThreadReadOnly, match="execution"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="execution")


def test_integration_thread_always_readonly(chat_service, project_id, root_node_id):
    with pytest.raises(ThreadReadOnly, match="integration"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="integration")


def test_ask_planning_writable_before_execution(chat_service, project_id, root_node_id):
    session = chat_service.get_session(project_id, root_node_id, thread_role="ask_planning")
    assert session["thread_role"] == "ask_planning"


def test_ask_planning_readonly_after_execution(chat_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )
    with pytest.raises(ThreadReadOnly, match="ask_planning"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="ask_planning")


def test_ask_planning_reset_readonly_after_execution(chat_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )
    with pytest.raises(ThreadReadOnly, match="ask_planning"):
        chat_service.reset_session(project_id, root_node_id, thread_role="ask_planning")


def test_audit_readonly_before_execution(chat_service, project_id, root_node_id):
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="audit")


def test_audit_writable_after_execution_completed(chat_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "completed",
            "initial_sha": "sha256:abc",
            "head_sha": "sha256:def",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
        },
    )
    chat_service._check_thread_writable(project_id, root_node_id, "audit")


def test_audit_readonly_during_execution(chat_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.create_message(project_id, root_node_id, "test", thread_role="audit")


def test_audit_reset_is_never_allowed(chat_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "completed",
            "initial_sha": "sha256:abc",
            "head_sha": "sha256:def",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
        },
    )
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.reset_session(project_id, root_node_id, thread_role="audit")


def test_package_audit_requires_rollup_package_record(chat_service, storage, project_id, root_node_id):
    snap = storage.project_store.load_snapshot(project_id)
    review_node_id = "review-001"
    snap["tree_state"]["node_index"][review_node_id] = {
        "node_id": review_node_id,
        "parent_id": root_node_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": 1,
        "display_order": 99,
        "hierarchical_number": "1.R",
        "created_at": "2026-01-01T00:00:00Z",
    }
    snap["tree_state"]["node_index"][root_node_id]["review_node_id"] = review_node_id
    storage.project_store.save_snapshot(project_id, snap)
    storage.review_state_store.write_state(
        project_id,
        review_node_id,
        {
            "checkpoints": [],
            "rollup": {
                "status": "accepted",
                "summary": "ready",
                "sha": "sha256:rollup",
                "accepted_at": "2026-01-01T01:00:00Z",
            },
            "pending_siblings": [],
        },
    )

    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service._check_thread_writable(project_id, root_node_id, "audit")

    audit_session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="audit")
    audit_session["messages"].append(
        {
            "message_id": AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
            "role": "assistant",
            "content": "Accepted rollup package",
            "status": "completed",
            "error": None,
            "turn_id": None,
            "created_at": "2026-01-01T01:00:00Z",
            "updated_at": "2026-01-01T01:00:00Z",
        }
    )
    storage.chat_state_store.write_session(project_id, root_node_id, audit_session, thread_role="audit")

    chat_service._check_thread_writable(project_id, root_node_id, "audit")


def test_live_turn_tracking_is_isolated_by_thread_role(chat_service, storage, project_id, root_node_id):
    audit_session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="audit")
    audit_session["active_turn_id"] = "audit-turn"
    audit_session["messages"] = [
        {
            "message_id": "audit-msg",
            "role": "assistant",
            "content": "",
            "status": "streaming",
            "error": None,
            "turn_id": "audit-turn",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    storage.chat_state_store.write_session(project_id, root_node_id, audit_session, thread_role="audit")

    with chat_service._live_turns_lock:
        chat_service._live_turns.add((project_id, root_node_id, "ask_planning", "ask-turn"))

    recovered = chat_service.get_session(project_id, root_node_id, thread_role="audit")
    assert recovered["active_turn_id"] is None
    assert recovered["messages"][0]["status"] == "error"
    assert recovered["messages"][0]["error"] is not None


def test_get_session_works_for_all_roles(chat_service, project_id, root_node_id):
    for role in ("ask_planning", "audit", "execution"):
        session = chat_service.get_session(project_id, root_node_id, thread_role=role)
        assert session["thread_role"] == role
