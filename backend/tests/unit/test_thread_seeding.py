from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import planningtree_workspace
from backend.services.chat_service import ChatService
from backend.services.execution_gating import AUDIT_FRAME_RECORD_MESSAGE_ID
from backend.services.project_service import ProjectService
from backend.services.thread_seed_service import (
    ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID,
    ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID,
    AUDIT_SEED_CHECKPOINT_MESSAGE_ID,
    AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID,
    AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID,
    INTEGRATION_SEED_CHECKPOINTS_MESSAGE_ID,
    INTEGRATION_SEED_CHILD_REVIEWS_MESSAGE_ID,
    INTEGRATION_SEED_GOAL_MESSAGE_ID,
    INTEGRATION_SEED_PARENT_FRAME_MESSAGE_ID,
    INTEGRATION_SEED_SPLIT_PACKAGE_MESSAGE_ID,
)
from backend.services.tree_service import TreeService
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


def _write_confirmed_frame(storage, project_id: str, node_id: str, content: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "confirmed_revision": 1,
                "confirmed_at": "2026-01-01T00:00:00Z",
                "confirmed_content": content,
            }
        ),
        encoding="utf-8",
    )


def _add_child(
    storage,
    project_id: str,
    parent_id: str,
    *,
    node_id: str,
    title: str,
    description: str,
    status: str = "ready",
) -> None:
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    parent = node_index[parent_id]
    parent["child_ids"] = [*parent.get("child_ids", []), node_id]
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    node_index[node_id] = {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": status,
        "node_kind": "original",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(parent["child_ids"]) - 1,
        "hierarchical_number": f"{parent_hnum}.{len(parent['child_ids'])}",
        "created_at": "2026-01-01T00:00:00Z",
    }
    storage.project_store.save_snapshot(project_id, snap)


def _add_review_node(storage, project_id: str, parent_id: str, review_id: str) -> None:
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    parent = node_index[parent_id]
    node_index[review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent.get('title', 'parent')}",
        "status": "ready",
        "node_kind": "review",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": 99,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.R",
        "created_at": "2026-01-01T00:00:00Z",
    }
    parent["review_node_id"] = review_id
    storage.project_store.save_snapshot(project_id, snap)


def test_audit_session_seeds_system_context_for_ready_child(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["title"] = "Authentication"
    snap["tree_state"]["node_index"][root_node_id]["description"] = "Parent auth package"
    storage.project_store.save_snapshot(project_id, snap)

    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-001",
        title="Implement auth guard",
        description="Add route guard middleware\n\nWhy now: Child owns request gating",
        status="ready",
    )
    _add_review_node(storage, project_id, root_node_id, "review-001")
    storage.review_state_store.write_state(
        project_id,
        "review-001",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:child-a",
                    "summary": "Auth base completed",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    session = chat_service.get_session(project_id, "child-001", thread_role="audit")

    assert [message["message_id"] for message in session["messages"]] == [
        AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID,
        AUDIT_SEED_CHECKPOINT_MESSAGE_ID,
        AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID,
    ]
    assert all(message["role"] == "system" for message in session["messages"])
    assert "Implement auth guard" in session["messages"][0]["content"]
    assert "Add route guard middleware" in session["messages"][0]["content"]
    assert "K1" in session["messages"][1]["content"]
    assert "sha256:child-a" in session["messages"][1]["content"]
    assert "Authentication" in session["messages"][2]["content"]


def test_ask_planning_session_seeds_checkpoint_handoff_and_reseeds_after_reset(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["title"] = "Authentication"
    snap["tree_state"]["node_index"][root_node_id]["description"] = "Parent auth package"
    storage.project_store.save_snapshot(project_id, snap)

    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-planning",
        title="Implement auth guard",
        description="Add route guard middleware\n\nWhy now: Child owns request gating",
        status="ready",
    )
    _add_review_node(storage, project_id, root_node_id, "review-planning")
    storage.review_state_store.write_state(
        project_id,
        "review-planning",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:child-a",
                    "summary": "Auth base completed",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    session = chat_service.get_session(project_id, "child-planning", thread_role="ask_planning")

    assert [message["message_id"] for message in session["messages"]] == [
        ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID,
        ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID,
    ]
    assert all(message["role"] == "system" for message in session["messages"])
    assert "Implement auth guard" in session["messages"][0]["content"]
    assert "K1" in session["messages"][1]["content"]
    assert "sha256:child-a" in session["messages"][1]["content"]
    assert "Auth base completed" in session["messages"][1]["content"]

    reset = chat_service.reset_session(project_id, "child-planning", thread_role="ask_planning")
    assert reset["messages"] == []

    reseeded = chat_service.get_session(project_id, "child-planning", thread_role="ask_planning")
    assert [message["message_id"] for message in reseeded["messages"]] == [
        ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID,
        ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID,
    ]


def test_audit_session_does_not_seed_locked_child_before_turn(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-locked",
        title="Locked child",
        description="Hidden work\n\nWhy now: Not yet",
        status="locked",
    )

    session = chat_service.get_session(project_id, "child-locked", thread_role="audit")

    assert session["messages"] == []


def test_audit_session_prepends_seed_messages_and_migrates_canonical_records_to_system(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["title"] = "Parent Task"
    snap["tree_state"]["node_index"][root_node_id]["description"] = "Parent summary"
    storage.project_store.save_snapshot(project_id, snap)

    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-002",
        title="Second child",
        description="Build the second unit\n\nWhy now: Follows the first unit",
        status="ready",
    )
    _add_review_node(storage, project_id, root_node_id, "review-002")
    storage.review_state_store.write_state(
        project_id,
        "review-002",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                }
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    audit_session = storage.chat_state_store.read_session(project_id, "child-002", thread_role="audit")
    audit_session["messages"] = [
        {
            "message_id": AUDIT_FRAME_RECORD_MESSAGE_ID,
            "role": "assistant",
            "content": "Canonical confirmed frame snapshot",
            "status": "completed",
            "error": None,
            "turn_id": "legacy-turn",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        {
            "message_id": "user-review",
            "role": "user",
            "content": "Please review this child.",
            "status": "completed",
            "error": None,
            "turn_id": "turn-1",
            "created_at": "2026-01-01T01:00:00Z",
            "updated_at": "2026-01-01T01:00:00Z",
        },
    ]
    storage.chat_state_store.write_session(project_id, "child-002", audit_session, thread_role="audit")

    session = chat_service.get_session(project_id, "child-002", thread_role="audit")

    assert [message["message_id"] for message in session["messages"][:4]] == [
        AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID,
        AUDIT_SEED_CHECKPOINT_MESSAGE_ID,
        AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID,
        AUDIT_FRAME_RECORD_MESSAGE_ID,
    ]
    assert session["messages"][3]["role"] == "system"
    assert session["messages"][3]["turn_id"] is None
    assert session["messages"][4]["message_id"] == "user-review"


def test_integration_session_seeds_system_context_when_rollup_ready(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["title"] = "Build authentication package"
    snap["tree_state"]["node_index"][root_node_id]["description"] = "Top-level auth delivery"
    storage.project_store.save_snapshot(project_id, snap)

    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-a",
        title="Auth guard",
        description="Implement route guard\n\nWhy now: Establish gating",
        status="done",
    )
    _add_child(
        storage,
        project_id,
        root_node_id,
        node_id="child-b",
        title="Session parser",
        description="Parse auth session cookie\n\nWhy now: Needed after gating",
        status="done",
    )
    _add_review_node(storage, project_id, root_node_id, "review-ready")
    storage.review_state_store.write_state(
        project_id,
        "review-ready",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:k0",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:k1",
                    "summary": "Auth guard accepted",
                    "source_node_id": "child-a",
                    "accepted_at": "2026-01-01T01:00:00Z",
                },
                {
                    "label": "K2",
                    "sha": "sha256:k2",
                    "summary": "Session parser accepted",
                    "source_node_id": "child-b",
                    "accepted_at": "2026-01-01T02:00:00Z",
                },
            ],
            "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )
    _write_confirmed_frame(
        storage,
        project_id,
        root_node_id,
        "# Parent Frame\nShip the authentication package.\n",
    )

    session = chat_service.get_session(project_id, "review-ready", thread_role="integration")

    assert [message["message_id"] for message in session["messages"]] == [
        INTEGRATION_SEED_PARENT_FRAME_MESSAGE_ID,
        INTEGRATION_SEED_SPLIT_PACKAGE_MESSAGE_ID,
        INTEGRATION_SEED_CHECKPOINTS_MESSAGE_ID,
        INTEGRATION_SEED_CHILD_REVIEWS_MESSAGE_ID,
        INTEGRATION_SEED_GOAL_MESSAGE_ID,
    ]
    assert all(message["role"] == "system" for message in session["messages"])
    assert "Ship the authentication package" in session["messages"][0]["content"]
    assert "Auth guard" in session["messages"][1]["content"]
    assert "K2" in session["messages"][2]["content"]
    assert "Session parser accepted" in session["messages"][3]["content"]


def test_integration_session_stays_empty_before_rollup_ready(
    chat_service,
    storage,
    project_id,
    root_node_id,
):
    _add_review_node(storage, project_id, root_node_id, "review-pending")
    storage.review_state_store.write_state(
        project_id,
        "review-pending",
        {
            "checkpoints": [],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    session = chat_service.get_session(project_id, "review-pending", thread_role="integration")

    assert session["messages"] == []
