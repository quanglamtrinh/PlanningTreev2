from __future__ import annotations

from backend.services.review_sibling_manifest import derive_review_sibling_manifest


def _node(
    node_id: str,
    *,
    parent_id: str | None,
    node_kind: str = "original",
    display_order: int = 0,
    title: str | None = None,
    description: str = "",
    child_ids: list[str] | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": child_ids or [],
        "title": title or node_id,
        "description": description,
        "status": "ready",
        "node_kind": node_kind,
        "depth": 0 if parent_id is None else 1,
        "display_order": display_order,
        "hierarchical_number": "1",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_derive_manifest_for_initial_lazy_split():
    parent = _node("root", parent_id=None, child_ids=["child-a"])
    child_a = _node(
        "child-a",
        parent_id="root",
        display_order=0,
        title="Subtask A",
        description="Do part A",
    )
    review = _node("review-1", parent_id="root", node_kind="review", title="Review")
    snapshot = {
        "tree_state": {
            "node_index": {
                "root": parent,
                "child-a": child_a,
                "review-1": review,
            }
        }
    }
    review_state = {
        "checkpoints": [
            {
                "label": "K0",
                "sha": "sha256:k0",
                "summary": None,
                "source_node_id": None,
                "accepted_at": "2026-01-01T00:00:00Z",
            }
        ],
        "pending_siblings": [
            {
                "index": 2,
                "title": "Subtask B",
                "objective": "Do part B",
                "materialized_node_id": None,
            },
            {
                "index": 3,
                "title": "Subtask C",
                "objective": "Do part C",
                "materialized_node_id": None,
            },
        ],
        "rollup": {"status": "pending"},
    }

    manifest = derive_review_sibling_manifest(snapshot, parent, review, review_state)

    assert manifest == [
        {
            "index": 1,
            "title": "Subtask A",
            "objective": "Do part A",
            "materialized_node_id": "child-a",
            "status": "active",
            "checkpoint_label": None,
        },
        {
            "index": 2,
            "title": "Subtask B",
            "objective": "Do part B",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
        {
            "index": 3,
            "title": "Subtask C",
            "objective": "Do part C",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
    ]


def test_derive_manifest_after_accept_and_next_materialization():
    parent = _node("root", parent_id=None, child_ids=["child-a", "child-b"])
    child_a = _node(
        "child-a",
        parent_id="root",
        display_order=0,
        title="Subtask A",
        description="Do part A",
    )
    child_b = _node(
        "child-b",
        parent_id="root",
        display_order=1,
        title="Subtask B",
        description="Do part B",
    )
    review = _node("review-1", parent_id="root", node_kind="review", title="Review")
    snapshot = {
        "tree_state": {
            "node_index": {
                "root": parent,
                "child-a": child_a,
                "child-b": child_b,
                "review-1": review,
            }
        }
    }
    review_state = {
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
                "summary": "Accepted A",
                "source_node_id": "child-a",
                "accepted_at": "2026-01-01T00:10:00Z",
            },
        ],
        "pending_siblings": [
            {
                "index": 2,
                "title": "Subtask B",
                "objective": "Do part B",
                "materialized_node_id": "child-b",
            },
            {
                "index": 3,
                "title": "Subtask C",
                "objective": "Do part C",
                "materialized_node_id": None,
            },
        ],
        "rollup": {"status": "pending"},
    }

    manifest = derive_review_sibling_manifest(snapshot, parent, review, review_state)

    assert manifest == [
        {
            "index": 1,
            "title": "Subtask A",
            "objective": "Do part A",
            "materialized_node_id": "child-a",
            "status": "completed",
            "checkpoint_label": "K1",
        },
        {
            "index": 2,
            "title": "Subtask B",
            "objective": "Do part B",
            "materialized_node_id": "child-b",
            "status": "active",
            "checkpoint_label": None,
        },
        {
            "index": 3,
            "title": "Subtask C",
            "objective": "Do part C",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
    ]
