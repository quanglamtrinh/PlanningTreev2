"""Tests for FinishTaskService precondition validation and state transitions."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import FinishTaskNotAllowed
from backend.services.finish_task_service import FinishTaskService
from backend.services.node_detail_service import NodeDetailService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage


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
def detail_service(storage, tree_service):
    return NodeDetailService(storage, tree_service)


@pytest.fixture
def finish_service(storage, tree_service, detail_service):
    return FinishTaskService(storage, tree_service, detail_service)


def _confirm_spec(storage, project_id, node_id):
    """Helper: confirm frame and spec so Finish Task preconditions can pass."""
    from backend.services.node_detail_service import NodeDetailService
    from backend.services import planningtree_workspace
    tree_svc = TreeService()
    detail_svc = NodeDetailService(storage, tree_svc)

    def _get_node_dir():
        snap = storage.project_store.load_snapshot(project_id)
        project = snap.get("project", {})
        project_path = Path(project.get("project_path", ""))
        return planningtree_workspace.resolve_node_dir(project_path, snap, node_id)

    # Write frame content
    node_dir = _get_node_dir()
    frame_path = node_dir / "frame.md"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text("# Task Title\nTest Task\n\n# Objective\nDo something\n", encoding="utf-8")

    detail_svc.confirm_frame(project_id, node_id)

    # Re-resolve node_dir after confirm_frame (title sync may rename directory)
    node_dir = _get_node_dir()
    spec_path = node_dir / "spec.md"
    spec_path.write_text("# Spec\nImplement the thing\n", encoding="utf-8")
    detail_svc.confirm_spec(project_id, node_id)

    # Set node status to "ready" so Finish Task precondition 3 can pass
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snap)


# ── Precondition failures ────────────────────────────────────────

def test_finish_task_fails_spec_not_confirmed(finish_service, project_id, root_node_id):
    with pytest.raises(FinishTaskNotAllowed, match="Spec must be confirmed"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_not_leaf(finish_service, storage, project_id, root_node_id):
    """Finish Task fails if node has children."""
    _confirm_spec(storage, project_id, root_node_id)
    # Add a child
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    root = node_index[root_node_id]
    child_id = "child-001"
    node_index[child_id] = {
        "node_id": child_id, "parent_id": root_node_id, "child_ids": [],
        "title": "Child", "description": "", "status": "ready",
        "node_kind": "original", "depth": 1, "display_order": 0,
        "hierarchical_number": "1.1", "created_at": "2026-01-01T00:00:00Z",
    }
    root["child_ids"] = [child_id]
    storage.project_store.save_snapshot(project_id, snap)

    with pytest.raises(FinishTaskNotAllowed, match="leaf"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_wrong_status(finish_service, storage, project_id, root_node_id):
    """Finish Task fails if node status is not ready/in_progress."""
    _confirm_spec(storage, project_id, root_node_id)
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["status"] = "locked"
    storage.project_store.save_snapshot(project_id, snap)

    with pytest.raises(FinishTaskNotAllowed, match="status"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_already_executing(finish_service, storage, project_id, root_node_id):
    """Finish Task fails if execution_state already exists."""
    _confirm_spec(storage, project_id, root_node_id)
    storage.execution_state_store.write_state(project_id, root_node_id, {
        "status": "executing", "initial_sha": "sha256:abc",
        "head_sha": None, "started_at": "2026-01-01T00:00:00Z", "completed_at": None,
    })

    with pytest.raises(FinishTaskNotAllowed, match="already been started"):
        finish_service.finish_task(project_id, root_node_id)


# ── Happy path ───────────────────────────────────────────────────

def test_finish_task_success(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    result = finish_service.finish_task(project_id, root_node_id)

    # Execution state should be created
    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state is not None
    assert exec_state["status"] == "executing"
    assert exec_state["initial_sha"] is not None
    assert exec_state["head_sha"] is None
    assert exec_state["started_at"] is not None

    # Detail state should reflect execution
    assert result["execution_started"] is True
    assert result["shaping_frozen"] is True
    assert result["can_finish_task"] is False
    assert result["execution_status"] == "executing"


def test_finish_task_sets_node_status_in_progress(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    # Ensure status is ready
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snap)

    finish_service.finish_task(project_id, root_node_id)

    snap = storage.project_store.load_snapshot(project_id)
    assert snap["tree_state"]["node_index"][root_node_id]["status"] == "in_progress"


# ── Execution completion ─────────────────────────────────────────

def test_complete_execution(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    finish_service.finish_task(project_id, root_node_id)

    result = finish_service.complete_execution(project_id, root_node_id, head_sha="sha256:final")

    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state["status"] == "completed"
    assert exec_state["head_sha"] == "sha256:final"
    assert exec_state["completed_at"] is not None

    assert result["execution_completed"] is True
    assert result["audit_writable"] is True


def test_complete_execution_fails_not_executing(finish_service, storage, project_id, root_node_id):
    with pytest.raises(FinishTaskNotAllowed, match="No execution state"):
        finish_service.complete_execution(project_id, root_node_id)


def test_complete_execution_fails_already_completed(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    finish_service.finish_task(project_id, root_node_id)
    finish_service.complete_execution(project_id, root_node_id, head_sha="sha256:done")

    with pytest.raises(FinishTaskNotAllowed, match="expected 'executing'"):
        finish_service.complete_execution(project_id, root_node_id, head_sha="sha256:again")
