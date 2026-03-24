from __future__ import annotations

from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.snapshot_view_service import SnapshotViewService


def _make_snapshot(nodes: dict, root_node_id: str = "root-1") -> dict:
    return {
        "schema_version": 6,
        "project": {
            "id": "proj-1",
            "name": "test",
            "root_goal": "g",
            "project_path": "",
            "created_at": "t",
            "updated_at": "t",
        },
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
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1", title="Review"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    review = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == "review-1")
    assert review["node_kind"] == "review"


def test_review_node_has_null_workflow():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    review = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == "review-1")
    assert review["workflow"] is None


def test_review_node_is_not_superseded():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    review = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == "review-1")
    assert review["is_superseded"] is False


def test_review_node_included_in_registry():
    svc = SnapshotViewService()
    nodes = {
        "root-1": _base_node("root-1"),
        "child-1": _base_node("child-1", parent_id="root-1"),
        "review-1": _base_node("review-1", node_kind="review", parent_id="root-1"),
    }
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    ids = {n["node_id"] for n in result["tree_state"]["node_registry"]}
    assert "review-1" in ids
    assert len(ids) == 3


def test_task_nodes_still_get_workflow_dict():
    svc = SnapshotViewService()
    nodes = {"root-1": _base_node("root-1")}
    result = svc.to_public_snapshot("proj-1", _make_snapshot(nodes))
    root = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == "root-1")
    assert root["workflow"] is not None
    assert isinstance(root["workflow"], dict)
    assert root["workflow"]["frame_confirmed"] is False
    assert root["workflow"]["execution_started"] is False
    assert root["workflow"]["active_step"] == "frame"


def test_task_workflow_includes_execution_fields(storage, workspace_root, tree_service):
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    doc_service.put_document(
        project_id,
        root_id,
        "frame",
        "# Task Title\nTest Task\n\n# Task-Shaping Fields\n- target platform: web\n",
    )
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)
    doc_service.put_document(project_id, root_id, "spec", "# Spec\nImplement it\n")
    detail_service.confirm_spec(project_id, root_id)

    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:start",
            "head_sha": "sha256:end",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
        },
    )

    svc = SnapshotViewService(storage)
    refreshed = storage.project_store.load_snapshot(project_id)
    result = svc.to_public_snapshot(project_id, refreshed)
    root = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == root_id)

    assert root["workflow"]["frame_confirmed"] is True
    assert root["workflow"]["spec_confirmed"] is True
    assert root["workflow"]["execution_started"] is True
    assert root["workflow"]["execution_completed"] is True
    assert root["workflow"]["shaping_frozen"] is True
    assert root["workflow"]["execution_status"] == "completed"


def test_review_summary_includes_derived_sibling_manifest(storage, workspace_root):
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    internal = storage.project_store.load_snapshot(project_id)
    node_index = internal["tree_state"]["node_index"]
    root = node_index[root_id]

    child_id = "child-a"
    review_id = "review-1"
    root["child_ids"] = [child_id]
    root["review_node_id"] = review_id
    node_index[child_id] = _base_node(
        child_id,
        parent_id=root_id,
        title="Subtask A",
        description="Do part A",
        depth=1,
        display_order=0,
        hierarchical_number="1.1",
    )
    node_index[review_id] = _base_node(
        review_id,
        parent_id=root_id,
        node_kind="review",
        title="Review",
        depth=1,
        display_order=99,
        hierarchical_number="1.R",
    )
    storage.project_store.save_snapshot(project_id, internal)

    storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:init",
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
                }
            ],
            "rollup": {"status": "pending"},
        },
    )

    svc = SnapshotViewService(storage)
    refreshed = storage.project_store.load_snapshot(project_id)
    result = svc.to_public_snapshot(project_id, refreshed)
    review = next(n for n in result["tree_state"]["node_registry"] if n["node_id"] == review_id)

    summary = review["review_summary"]
    assert summary is not None
    assert summary["pending_sibling_count"] == 1
    assert summary["sibling_manifest"] == [
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
    ]
