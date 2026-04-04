"""Tests for ChatService thread read-only enforcement."""
from __future__ import annotations

import pytest

from backend.errors.app_errors import InvalidRequest, ThreadReadOnly
from backend.services.chat_service import ChatService
from backend.services.execution_gating import AUDIT_ROLLUP_PACKAGE_MESSAGE_ID
from backend.services.project_service import ProjectService
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.streaming.sse_broker import ChatEventBroker


class FakeReadonlyCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[str] = []
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"audit-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"ask-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        return {
            "stdout": "READY",
            "thread_id": str(kwargs.get("thread_id") or ""),
            "turn_status": "completed",
        }


@pytest.fixture
def project_id(storage, workspace_root):
    snap = ProjectService(storage).attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


@pytest.fixture
def root_node_id(storage, project_id):
    snap = storage.project_store.load_snapshot(project_id)
    return snap["tree_state"]["root_node_id"]


@pytest.fixture
def review_node_id(storage, project_id, root_node_id):
    review_id = "review-001"
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][review_id] = {
        "node_id": review_id,
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
    snap["tree_state"]["node_index"][root_node_id]["review_node_id"] = review_id
    storage.project_store.save_snapshot(project_id, snap)
    return review_id


@pytest.fixture
def chat_service(storage, tree_service):
    codex_client = FakeReadonlyCodexClient()
    return ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, TreeService()),
        chat_event_broker=ChatEventBroker(),
        chat_timeout=30,
    )


def test_execution_thread_is_writable(chat_service, project_id, root_node_id):
    chat_service._check_thread_writable(project_id, root_node_id, "execution")


def test_review_audit_thread_always_readonly(chat_service, project_id, review_node_id):
    with pytest.raises(ThreadReadOnly, match="audit"):
        chat_service.create_message(project_id, review_node_id, "test", thread_role="audit")


def test_task_node_rejects_integration_thread_role(chat_service, project_id, root_node_id):
    with pytest.raises(InvalidRequest, match="Invalid thread_role"):
        chat_service.get_session(project_id, root_node_id, thread_role="integration")


@pytest.mark.parametrize("thread_role", ["ask_planning", "execution", "integration"])
def test_review_node_rejects_non_audit_thread_roles(chat_service, project_id, review_node_id, thread_role):
    match = "Invalid thread_role" if thread_role == "integration" else "not valid for node_kind"
    with pytest.raises(InvalidRequest, match=match):
        chat_service.get_session(project_id, review_node_id, thread_role=thread_role)


def test_review_node_allows_audit_session(chat_service, project_id, review_node_id):
    session = chat_service.get_session(project_id, review_node_id, thread_role="audit")
    assert session["thread_role"] == "audit"


def test_unknown_thread_role_is_rejected(chat_service, project_id, root_node_id):
    with pytest.raises(InvalidRequest, match="Invalid thread_role"):
        chat_service.get_session(project_id, root_node_id, thread_role="foo")


def test_ask_planning_writable_before_execution(chat_service, project_id, root_node_id):
    session = chat_service.get_session(project_id, root_node_id, thread_role="ask_planning")
    assert session["thread_role"] == "ask_planning"


def test_ask_planning_writable_after_execution(chat_service, storage, project_id, root_node_id):
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
    chat_service.create_message(project_id, root_node_id, "test", thread_role="ask_planning")


def test_ask_planning_reset_allowed_after_execution(chat_service, storage, project_id, root_node_id):
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
    session = chat_service.reset_session(project_id, root_node_id, thread_role="ask_planning")
    assert session["thread_role"] == "ask_planning"


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


def test_package_audit_requires_rollup_package_record(
    chat_service, storage, project_id, root_node_id, review_node_id
):
    snap = storage.project_store.load_snapshot(project_id)
    assert snap["tree_state"]["node_index"][root_node_id]["review_node_id"] == review_node_id
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


def test_get_session_works_for_all_task_roles(chat_service, project_id, root_node_id):
    for role in ("ask_planning", "audit", "execution"):
        session = chat_service.get_session(project_id, root_node_id, thread_role=role)
        assert session["thread_role"] == role
