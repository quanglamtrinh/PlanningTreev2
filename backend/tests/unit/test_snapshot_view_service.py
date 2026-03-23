from __future__ import annotations

from backend.services.snapshot_view_service import SnapshotViewService


def _make_snapshot(nodes: dict, root_node_id: str = "root-1") -> dict:
    """Build a minimal internal snapshot with the given node_index."""
    return {
        "schema_version": 6,
        "project": {"id": "proj-1", "name": "test", "root_goal": "g",
                     "project_path": "", "created_at": "t", "updated_at": "t"},
        "tree_state": {
            "root_node_id": root_node_id,
            "active_node_id": None,
            "node_index": nodes,
        },
        "updated_at": "t",
    }


def _base_node(node_id: str, **overrides) -> dict:
    base = {
        "node_id": node_id,
        "parent_id": None,
        "child_ids": [],
        "title": f"Node {node_id}",
        "description": "",
        "status": "ready",
        "node_kind": "original",
        "depth": 0,
        "display_order": 0,
        "hierarchical_number": "1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_review_node_keeps_kind_review():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1",
                               title="Review", status="ready"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    registry = result["tree_state"]["node_registry"]
    review = next(n for n in registry if n["node_id"] == "review-1")

    assert review["node_kind"] == "review"


def test_review_node_has_null_workflow():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    registry = result["tree_state"]["node_registry"]
    review = next(n for n in registry if n["node_id"] == "review-1")

    assert review["workflow"] is None


def test_review_node_is_not_superseded():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    registry = result["tree_state"]["node_registry"]
    review = next(n for n in registry if n["node_id"] == "review-1")

    assert review["is_superseded"] is False


def test_review_node_included_in_registry():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "child-1": _base_node("child-1", parent_id="root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    registry = result["tree_state"]["node_registry"]
    ids = {n["node_id"] for n in registry}

    assert "review-1" in ids
    assert len(registry) == 3


def test_task_nodes_still_get_workflow_dict():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    registry = result["tree_state"]["node_registry"]
    root = next(n for n in registry if n["node_id"] == "root-1")

    # Task nodes should have a workflow dict (not None)
    assert root["workflow"] is not None
    assert isinstance(root["workflow"], dict)
