from __future__ import annotations

import pytest

from backend.errors.app_errors import ConfirmationNotAllowed
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def set_task(
    storage: Storage,
    project_id: str,
    node_id: str,
    *,
    title: str,
    purpose: str,
    responsibility: str = "",
) -> None:
    storage.node_store.save_task(
        project_id,
        node_id,
        {
            "title": title,
            "purpose": purpose,
            "responsibility": responsibility,
        },
    )


def set_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def test_confirm_task_requires_non_empty_title(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_task(storage, project_id, root_id, title="", purpose="Still has purpose")

    with pytest.raises(ConfirmationNotAllowed, match="non-empty title"):
        node_service.confirm_task(project_id, root_id)


def test_confirm_task_requires_non_empty_purpose(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_task(storage, project_id, root_id, title="Alpha", purpose="")

    with pytest.raises(ConfirmationNotAllowed, match="non-empty purpose"):
        node_service.confirm_task(project_id, root_id)


def test_confirm_task_advances_phase_and_is_idempotent(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    state = node_service.confirm_task(project_id, root_id)
    assert state["task_confirmed"] is True
    assert state["phase"] == "spec_review"
    assert state["brief_generation_status"] == "ready"
    assert state["spec_initialized"] is True

    repeated = node_service.confirm_task(project_id, root_id)
    assert repeated["task_confirmed"] is True
    assert repeated["phase"] == "spec_review"

    persisted = storage.project_store.load_snapshot(project_id)
    assert persisted["tree_state"]["node_index"][root_id]["phase"] == "spec_review"


def test_confirm_task_retries_failed_brief_pipeline_from_awaiting_brief(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    state = storage.node_store.load_state(project_id, root_id)
    state["task_confirmed"] = True
    state["phase"] = "awaiting_brief"
    state["brief_generation_status"] = "failed"
    storage.node_store.save_state(project_id, root_id, state)
    set_phase(storage, project_id, root_id, "awaiting_brief")

    retried = node_service.confirm_task(project_id, root_id)

    assert retried["task_confirmed"] is True
    assert retried["phase"] == "spec_review"
    assert retried["brief_generation_status"] == "ready"
    assert retried["spec_initialized"] is True


def test_confirm_briefing_requires_brief_to_exist(
    project_service: ProjectService,
    node_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    with pytest.raises(ConfirmationNotAllowed, match="Brief does not exist"):
        node_service.confirm_briefing(project_id, root_id)


def test_confirm_briefing_is_compatibility_no_op_once_brief_exists(
    project_service: ProjectService,
    node_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    state = node_service.confirm_briefing(project_id, root_id)
    assert state["brief_generation_status"] == "ready"
    assert state["phase"] == "spec_review"


def test_confirm_spec_confirms_initialized_spec_and_advances_to_ready_for_execution(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    task_state = node_service.confirm_task(project_id, root_id)
    assert task_state["spec_initialized"] is True
    spec_state = node_service.confirm_spec(project_id, root_id)
    assert spec_state["spec_confirmed"] is True
    assert spec_state["phase"] == "ready_for_execution"
    assert spec_state["active_spec_version"] == 1

    persisted_state = storage.node_store.load_state(project_id, root_id)
    assert persisted_state["phase"] == "ready_for_execution"
    persisted_snapshot = storage.project_store.load_snapshot(project_id)
    assert persisted_snapshot["tree_state"]["node_index"][root_id]["phase"] == "ready_for_execution"
