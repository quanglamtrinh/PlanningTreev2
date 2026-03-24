from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import ReviewNotAllowed
from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.review_service import ReviewService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage


# ── Helpers ──────────────────────────────────────────────────────


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def make_node_split_ready(
    storage: Storage,
    tree_service: TreeService,
    project_id: str,
    node_id: str,
) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    title = str(snapshot["tree_state"]["node_index"][node_id]["title"])
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    doc_service.put_document(
        project_id,
        node_id,
        "frame",
        (
            f"# Task Title\n{title}\n\n"
            "# Task-Shaping Fields\n"
            "- target platform: web\n"
        ),
    )
    detail_service.bump_frame_revision(project_id, node_id)
    state = detail_service.confirm_frame(project_id, node_id)
    assert state["active_step"] == "spec"


def simulate_execution_completed(
    storage: Storage, project_id: str, node_id: str, head_sha: str = "sha256:abc123"
) -> None:
    """Simulate a node that has gone through Finish Task and completed execution."""
    storage.execution_state_store.write_state(
        project_id,
        node_id,
        {
            "status": "completed",
            "initial_sha": "sha256:initial000",
            "head_sha": head_sha,
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )


def simulate_full_child_lifecycle(
    storage: Storage,
    tree_service: TreeService,
    review_service: ReviewService,
    project_id: str,
    node_id: str,
    summary: str = "Work completed.",
    head_sha: str = "sha256:child_done",
) -> dict:
    """Make node split-ready, simulate execution, start+accept local review."""
    make_node_split_ready(storage, tree_service, project_id, node_id)
    # Simulate spec confirmation
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    doc_service.put_document(
        project_id, node_id, "spec", "# Overview\nDo the thing.\n"
    )
    detail_service.confirm_spec(project_id, node_id)
    simulate_execution_completed(storage, project_id, node_id, head_sha)
    review_service.start_local_review(project_id, node_id)
    return review_service.accept_local_review(project_id, node_id, summary)


# ── Fake split helper ────────────────────────────────────────────


def do_lazy_split(
    storage: Storage,
    tree_service: TreeService,
    project_id: str,
    node_id: str,
    subtask_count: int = 2,
) -> dict:
    """Perform a lazy split by directly writing to storage (no Codex needed)."""
    from uuid import uuid4
    from backend.services.workspace_sha import compute_workspace_sha

    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = tree_service.node_index(snapshot)
    parent = node_by_id[node_id]
    now = iso_now()
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)

    subtasks = [
        {"title": f"Subtask {i}", "objective": f"Do subtask {i}.", "why_now": f"Step {i}."}
        for i in range(1, subtask_count + 1)
    ]

    # First child
    first_child_id = uuid4().hex
    first_child = {
        "node_id": first_child_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": subtasks[0]["title"],
        "description": subtasks[0]["objective"],
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.1",
        "created_at": now,
    }
    parent.setdefault("child_ids", []).append(first_child_id)
    snapshot["tree_state"]["node_index"][first_child_id] = first_child

    # Review node
    review_node_id = uuid4().hex
    review_node = {
        "node_id": review_node_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": now,
    }
    snapshot["tree_state"]["node_index"][review_node_id] = review_node
    parent["review_node_id"] = review_node_id

    # K0 checkpoint
    workspace_root = str(snapshot["project"]["project_path"])
    k0_sha = compute_workspace_sha(Path(workspace_root))

    pending_siblings = [
        {
            "index": i,
            "title": subtasks[i - 1]["title"],
            "objective": subtasks[i - 1]["objective"],
            "materialized_node_id": None,
        }
        for i in range(2, subtask_count + 1)
    ]

    review_state = {
        "checkpoints": [
            {
                "label": "K0",
                "sha": k0_sha,
                "summary": None,
                "source_node_id": None,
                "accepted_at": now,
            }
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": pending_siblings,
    }
    storage.review_state_store.write_state(project_id, review_node_id, review_state)

    if parent.get("status") in {"ready", "in_progress"}:
        parent["status"] = "draft"
    snapshot["tree_state"]["active_node_id"] = first_child_id
    snapshot["updated_at"] = now
    storage.project_store.save_snapshot(project_id, snapshot)

    # Sync workspace dirs
    planningtree_workspace.sync_snapshot_tree(Path(workspace_root), snapshot)

    return {
        "first_child_id": first_child_id,
        "review_node_id": review_node_id,
        "k0_sha": k0_sha,
    }


# ── Tests: start_local_review ────────────────────────────────────


def test_start_local_review_transitions_completed_to_review_pending(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    simulate_execution_completed(storage, project_id, root_id)

    result = review_service.start_local_review(project_id, root_id)
    assert result["status"] == "review_pending"

    # Verify persisted
    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_pending"


def test_start_local_review_rejects_non_completed_status(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = ReviewService(storage, TreeService())

    # No execution state at all
    with pytest.raises(ReviewNotAllowed, match="No execution state"):
        review_service.start_local_review(project_id, root_id)

    # Executing (not completed)
    storage.execution_state_store.write_state(
        project_id, root_id, {"status": "executing", "started_at": iso_now()}
    )
    with pytest.raises(ReviewNotAllowed, match="executing"):
        review_service.start_local_review(project_id, root_id)


# ── Tests: accept_local_review ────────────────────────────────────


def test_accept_local_review_transitions_to_review_accepted_and_marks_done(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    simulate_execution_completed(storage, project_id, root_id)
    review_service.start_local_review(project_id, root_id)

    result = review_service.accept_local_review(project_id, root_id, "Looks good.")
    assert result["status"] == "review_accepted"

    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_accepted"

    persisted = storage.project_store.load_snapshot(project_id)
    node = persisted["tree_state"]["node_index"][root_id]
    assert node["status"] == "done"


def test_accept_local_review_rejects_empty_summary(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = ReviewService(storage, TreeService())

    simulate_execution_completed(storage, project_id, root_id)
    review_service.start_local_review(project_id, root_id)

    with pytest.raises(ReviewNotAllowed, match="non-empty summary"):
        review_service.accept_local_review(project_id, root_id, "")

    with pytest.raises(ReviewNotAllowed, match="non-empty summary"):
        review_service.accept_local_review(project_id, root_id, "   ")


def test_accept_local_review_rejects_non_review_pending(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = ReviewService(storage, TreeService())

    simulate_execution_completed(storage, project_id, root_id)
    # Status is "completed", not "review_pending"
    with pytest.raises(ReviewNotAllowed, match="completed"):
        review_service.accept_local_review(project_id, root_id, "Summary")


# ── Tests: checkpoint progression ─────────────────────────────────


def test_accept_local_review_appends_checkpoint_to_review_node(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child's execution and review
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_head")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "First child done.")

    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert len(review_state["checkpoints"]) == 2
    assert review_state["checkpoints"][0]["label"] == "K0"
    assert review_state["checkpoints"][1]["label"] == "K1"
    assert review_state["checkpoints"][1]["sha"] == "sha256:child1_head"
    assert review_state["checkpoints"][1]["summary"] == "First child done."
    assert review_state["checkpoints"][1]["source_node_id"] == first_child_id


# ── Tests: lazy sibling activation ────────────────────────────────


def test_accept_local_review_activates_next_sibling(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=3)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_done")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")

    # Should have activated sibling 2
    activated_id = result["activated_sibling_id"]
    assert activated_id is not None

    persisted = storage.project_store.load_snapshot(project_id)
    node_index = persisted["tree_state"]["node_index"]
    parent = node_index[root_id]

    # Parent should have 2 children now
    assert len(parent["child_ids"]) == 2
    assert parent["child_ids"][1] == activated_id

    # Activated sibling should be ready
    sibling = node_index[activated_id]
    assert sibling["status"] == "ready"
    assert sibling["title"] == "Subtask 2"
    assert sibling["hierarchical_number"].endswith(".2")

    # Should be the active node
    assert persisted["tree_state"]["active_node_id"] == activated_id

    # Manifest should show materialized
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    materialized = [
        s for s in review_state["pending_siblings"] if s["materialized_node_id"] is not None
    ]
    assert len(materialized) == 1
    assert materialized[0]["materialized_node_id"] == activated_id


# ── Tests: legacy eager path ─────────────────────────────────────


def test_accept_local_review_unlocks_legacy_eager_sibling(
    storage: Storage, workspace_root,
) -> None:
    """Legacy trees without review_node_id should unlock next locked sibling."""
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    # Manually create legacy eager children
    persisted = storage.project_store.load_snapshot(project_id)
    node_index = persisted["tree_state"]["node_index"]
    parent = node_index[root_id]
    now = iso_now()

    child_a_id = "legacy_child_a"
    child_b_id = "legacy_child_b"
    node_index[child_a_id] = {
        "node_id": child_a_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child A",
        "description": "First child",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
        "created_at": now,
    }
    node_index[child_b_id] = {
        "node_id": child_b_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child B",
        "description": "Second child",
        "status": "locked",
        "node_kind": "original",
        "depth": 1,
        "display_order": 1,
        "hierarchical_number": "1.2",
        "created_at": now,
    }
    parent["child_ids"] = [child_a_id, child_b_id]
    parent["status"] = "draft"
    persisted["tree_state"]["active_node_id"] = child_a_id
    storage.project_store.save_snapshot(project_id, persisted)

    # Complete child A
    simulate_execution_completed(storage, project_id, child_a_id)
    review_service.start_local_review(project_id, child_a_id)
    result = review_service.accept_local_review(project_id, child_a_id, "Legacy child done.")

    # Child B should be unlocked
    persisted = storage.project_store.load_snapshot(project_id)
    child_b = persisted["tree_state"]["node_index"][child_b_id]
    assert child_b["status"] == "ready"
    assert persisted["tree_state"]["active_node_id"] == child_b_id


# ── Tests: rollup readiness ──────────────────────────────────────


def test_rollup_becomes_ready_when_all_siblings_accepted(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child -> activates second
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:c1")
    review_service.start_local_review(project_id, first_child_id)
    result1 = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")
    second_child_id = result1["activated_sibling_id"]
    assert second_child_id is not None

    # Rollup should still be pending
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "pending"

    # Complete second child
    simulate_execution_completed(storage, project_id, second_child_id, "sha256:c2")
    review_service.start_local_review(project_id, second_child_id)
    review_service.accept_local_review(project_id, second_child_id, "Child 2 done.")

    # Rollup should now be ready
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "ready"

    # Checkpoint chain: K0, K1, K2
    assert len(review_state["checkpoints"]) == 3
    assert review_state["checkpoints"][2]["label"] == "K2"


# ── Tests: accept_rollup_review ──────────────────────────────────


def test_accept_rollup_review_sets_accepted_and_appends_to_parent_audit(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete both children to get rollup to "ready"
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:c1")
    review_service.start_local_review(project_id, first_child_id)
    result1 = review_service.accept_local_review(project_id, first_child_id, "C1 done.")
    second_child_id = result1["activated_sibling_id"]
    assert second_child_id is not None

    simulate_execution_completed(storage, project_id, second_child_id, "sha256:c2")
    review_service.start_local_review(project_id, second_child_id)
    review_service.accept_local_review(project_id, second_child_id, "C2 done.")

    # Accept rollup
    result = review_service.accept_rollup_review(
        project_id, review_node_id, "Integration looks good."
    )
    assert result["rollup_status"] == "accepted"
    assert result["summary"] == "Integration looks good."
    assert result["sha"].startswith("sha256:")

    # Verify review state
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "accepted"
    assert review_state["rollup"]["summary"] == "Integration looks good."

    # Verify parent audit has rollup package
    audit_session = storage.chat_state_store.read_session(
        project_id, root_id, thread_role="audit"
    )
    messages = audit_session.get("messages", [])
    rollup_msgs = [m for m in messages if m.get("message_id") == "audit-package:rollup"]
    assert len(rollup_msgs) == 1
    assert "Integration looks good." in rollup_msgs[0]["content"]


def test_accept_rollup_review_rejects_non_ready(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    review_node_id = split_result["review_node_id"]

    # Rollup is still "pending"
    with pytest.raises(ReviewNotAllowed, match="pending"):
        review_service.accept_rollup_review(
            project_id, review_node_id, "Too early."
        )


def test_accept_rollup_review_rejects_empty_summary(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = ReviewService(storage, TreeService())

    # Manually set rollup to ready
    split_result = do_lazy_split(storage, TreeService(), project_id, root_id, subtask_count=1)
    review_node_id = split_result["review_node_id"]
    storage.review_state_store.set_rollup(project_id, review_node_id, "ready")

    with pytest.raises(ReviewNotAllowed, match="non-empty summary"):
        review_service.accept_rollup_review(project_id, review_node_id, "")


# ── Tests: single-child split ────────────────────────────────────


def test_single_child_split_rollup_ready_after_one_review(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = ReviewService(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # No pending siblings — rollup should become ready after one child
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only_child")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    # No sibling to activate
    assert result["activated_sibling_id"] is None

    # Rollup should be ready
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "ready"
