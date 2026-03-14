from __future__ import annotations

from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def confirm_through_spec(node_service, project_id: str, node_id: str) -> None:
    node_service.confirm_task(project_id, node_id)
    node_service.confirm_briefing(project_id, node_id)
    node_service.update_spec(project_id, node_id, {"business_contract": "Ready to execute."})
    node_service.confirm_spec(project_id, node_id)


def test_edit_task_after_confirmation_resets_downstream_flags_and_phase(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    confirm_through_spec(node_service, project_id, root_id)

    node_service.update_task(project_id, root_id, {"purpose": "Updated purpose."})

    state = storage.node_store.load_state(project_id, root_id)
    assert state["task_confirmed"] is False
    assert state["briefing_confirmed"] is False
    assert state["spec_confirmed"] is False
    assert state["phase"] == "planning"
    assert state["spec_generated"] is True


def test_edit_briefing_after_confirmation_steps_back_to_briefing_review(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    confirm_through_spec(node_service, project_id, root_id)

    node_service.update_briefing(project_id, root_id, {"user_notes": "New briefing note."})

    state = storage.node_store.load_state(project_id, root_id)
    assert state["task_confirmed"] is True
    assert state["briefing_confirmed"] is False
    assert state["spec_confirmed"] is False
    assert state["phase"] == "briefing_review"
    assert state["spec_generated"] is True


def test_edit_spec_after_confirmation_steps_back_to_spec_review(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    confirm_through_spec(node_service, project_id, root_id)

    node_service.update_spec(project_id, root_id, {"technical_contract": "Use a stable API."})

    state = storage.node_store.load_state(project_id, root_id)
    assert state["spec_confirmed"] is False
    assert state["phase"] == "spec_review"
    assert state["spec_generated"] is True


def test_unchanged_document_saves_do_not_clear_confirmations(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    confirm_through_spec(node_service, project_id, root_id)

    task = storage.node_store.load_task(project_id, root_id)
    briefing = storage.node_store.load_briefing(project_id, root_id)
    spec = storage.node_store.load_spec(project_id, root_id)

    node_service.update_task(project_id, root_id, {"title": task["title"]})
    node_service.update_briefing(project_id, root_id, {"user_notes": briefing["user_notes"]})
    node_service.update_spec(project_id, root_id, {"business_contract": spec["business_contract"]})

    state = storage.node_store.load_state(project_id, root_id)
    assert state["task_confirmed"] is True
    assert state["briefing_confirmed"] is True
    assert state["spec_confirmed"] is True
    assert state["phase"] == "ready_for_execution"


def test_editing_spec_sets_spec_generated_and_legacy_patch_resets_task_confirmation(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    node_service.update_spec(project_id, root_id, {"business_contract": "Generate a spec manually."})
    generated_state = storage.node_store.load_state(project_id, root_id)
    assert generated_state["spec_generated"] is True

    node_service.confirm_task(project_id, root_id)
    node_service.update_node(project_id, root_id, description="Clarified goal from compat patch.")

    compat_state = storage.node_store.load_state(project_id, root_id)
    assert compat_state["task_confirmed"] is False
    assert compat_state["phase"] == "planning"
    assert compat_state["spec_generated"] is True

