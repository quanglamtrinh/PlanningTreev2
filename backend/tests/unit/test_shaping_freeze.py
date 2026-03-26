"""Tests for shaping freeze enforcement across mutation entry points."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.errors.app_errors import ShapingFrozen
from backend.services.clarify_generation_service import ClarifyGenerationService
from backend.services.frame_generation_service import FrameGenerationService
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.split_service import SplitService
from backend.services.thread_lineage_service import ThreadLineageService
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
def detail_service(storage, tree_service):
    return NodeDetailService(storage, tree_service)


def _freeze_node(storage, project_id, node_id):
    storage.execution_state_store.write_state(
        project_id,
        node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )


def test_confirm_frame_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="confirm frame"):
        detail_service.confirm_frame(project_id, root_node_id)


def test_confirm_spec_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="confirm spec"):
        detail_service.confirm_spec(project_id, root_node_id)


def test_bump_frame_revision_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="save frame"):
        detail_service.bump_frame_revision(project_id, root_node_id)


def test_seed_clarify_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="seed clarify"):
        detail_service.seed_clarify(project_id, root_node_id)


def test_update_clarify_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="update clarify"):
        detail_service.update_clarify_answers(project_id, root_node_id, [])


def test_apply_clarify_blocked_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    with pytest.raises(ShapingFrozen, match="apply clarify"):
        detail_service.apply_clarify_to_frame(project_id, root_node_id)


def test_put_document_blocked_when_frozen(storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    doc_service = NodeDocumentService(storage)

    with pytest.raises(ShapingFrozen, match="save frame"):
        doc_service.put_document(project_id, root_node_id, "frame", "# Frame\nFrozen\n")


def test_put_spec_document_blocked_when_frozen(storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    doc_service = NodeDocumentService(storage)

    with pytest.raises(ShapingFrozen, match="save spec"):
        doc_service.put_document(project_id, root_node_id, "spec", "# Spec\nFrozen\n")


def test_generate_frame_blocked_when_frozen(storage, tree_service, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    service = FrameGenerationService(
        storage,
        tree_service,
        MagicMock(),
        thread_lineage_service=MagicMock(),
        frame_gen_timeout=5,
    )

    with pytest.raises(ShapingFrozen, match="generate frame"):
        service.generate_frame(project_id, root_node_id)


def test_generate_clarify_blocked_when_frozen(storage, tree_service, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    service = ClarifyGenerationService(
        storage,
        tree_service,
        MagicMock(),
        thread_lineage_service=MagicMock(),
        clarify_gen_timeout=5,
    )

    with pytest.raises(ShapingFrozen, match="generate clarify"):
        service.generate_clarify(project_id, root_node_id)


def test_generate_spec_blocked_when_frozen(storage, tree_service, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    service = SpecGenerationService(
        storage,
        tree_service,
        MagicMock(),
        thread_lineage_service=MagicMock(),
        spec_gen_timeout=5,
    )

    with pytest.raises(ShapingFrozen, match="generate spec"):
        service.generate_spec(project_id, root_node_id)


def test_split_blocked_when_frozen(storage, tree_service, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    codex_client = MagicMock()
    service = SplitService(
        storage,
        tree_service,
        codex_client,
        ThreadLineageService(storage, codex_client, tree_service),
        split_timeout=5,
    )

    with pytest.raises(ShapingFrozen, match="split"):
        service.split_node(project_id, root_node_id, "workflow")


def test_get_detail_state_works_when_frozen(detail_service, storage, project_id, root_node_id):
    _freeze_node(storage, project_id, root_node_id)
    state = detail_service.get_detail_state(project_id, root_node_id)
    assert state["shaping_frozen"] is True
    assert state["execution_started"] is True
    assert state["execution_status"] == "executing"
    assert state["workflow"] is not None
    assert state["workflow"]["execution_started"] == state["execution_started"]
    assert state["workflow"]["execution_completed"] == state["execution_completed"]
    assert state["workflow"]["shaping_frozen"] == state["shaping_frozen"]
    assert state["workflow"]["can_finish_task"] == state["can_finish_task"]
    assert state["workflow"]["execution_status"] == state["execution_status"]


def test_detail_state_before_execution(detail_service, project_id, root_node_id):
    state = detail_service.get_detail_state(project_id, root_node_id)
    assert state["shaping_frozen"] is False
    assert state["execution_started"] is False
    assert state["execution_status"] is None
    assert state["execution_completed"] is False
    assert state["audit_writable"] is False
    assert state["workflow"] is not None
    assert state["workflow"]["execution_started"] is False
    assert state["workflow"]["execution_completed"] is False
    assert state["workflow"]["shaping_frozen"] is False
    assert state["workflow"]["can_finish_task"] == state["can_finish_task"]
    assert state["workflow"]["execution_status"] is None


def test_review_detail_state_returns_null_workflow(
    detail_service,
    storage,
    project_id,
    review_node_id,
):
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

    state = detail_service.get_detail_state(project_id, review_node_id)
    assert state["workflow"] is None
    assert state["can_finish_task"] is False
    assert state["audit_writable"] is False
    assert state["review_status"] == "accepted"
