from __future__ import annotations

import pytest

from backend.errors.app_errors import InvalidRequest, NodeUpdateNotAllowed
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 4")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def mark_node(storage: Storage, project_id: str, node_id: str, **updates: object) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    node = snapshot["tree_state"]["node_index"][node_id]
    node.update(updates)
    storage.project_store.save_snapshot(project_id, snapshot)
    if "phase" in updates:
        state = storage.node_store.load_state(project_id, node_id)
        state["phase"] = updates["phase"]
        storage.node_store.save_state(project_id, node_id, state)


def test_get_documents_returns_all_node_documents(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    documents = node_service.get_documents(project_id, root_id)

    assert documents == {
        "task": {
            "title": "Alpha",
            "purpose": "Ship phase 4",
            "responsibility": "",
        },
        "brief": {
            "node_snapshot": {
                "node_summary": "",
                "why_this_node_exists_now": "",
                "current_focus": "",
            },
            "active_inherited_context": {
                "active_goals_from_parent": [],
                "active_constraints_from_parent": [],
                "active_decisions_in_force": [],
            },
            "accepted_upstream_facts": {
                "accepted_outputs": [],
                "available_artifacts": [],
                "confirmed_dependencies": [],
            },
            "runtime_state": {
                "status": "",
                "completed_so_far": [],
                "current_blockers": [],
                "next_best_action": "",
            },
            "pending_escalations": {
                "open_risks": [],
                "pending_user_decisions": [],
                "fallback_direction_if_unanswered": "",
            },
        },
        "briefing": {
            "node_snapshot": {
                "node_summary": "",
                "why_this_node_exists_now": "",
                "current_focus": "",
            },
            "active_inherited_context": {
                "active_goals_from_parent": [],
                "active_constraints_from_parent": [],
                "active_decisions_in_force": [],
            },
            "accepted_upstream_facts": {
                "accepted_outputs": [],
                "available_artifacts": [],
                "confirmed_dependencies": [],
            },
            "runtime_state": {
                "status": "",
                "completed_so_far": [],
                "current_blockers": [],
                "next_best_action": "",
            },
            "pending_escalations": {
                "open_risks": [],
                "pending_user_decisions": [],
                "fallback_direction_if_unanswered": "",
            },
        },
        "spec": {
            "mission": {
                "goal": "",
                "success_outcome": "",
                "implementation_level": "",
            },
            "scope": {
                "must_do": [],
                "must_not_do": [],
                "deferred_work": [],
            },
            "constraints": {
                "hard_constraints": [],
                "change_budget": "",
                "touch_boundaries": [],
                "external_dependencies": [],
            },
            "autonomy": {
                "allowed_decisions": [],
                "requires_confirmation": [],
                "default_policy_when_unclear": "",
            },
            "verification": {
                "acceptance_checks": [],
                "definition_of_done": "",
                "evidence_expected": [],
            },
            "execution_controls": {
                "quality_profile": "",
                "tooling_limits": [],
                "output_expectation": "",
                "conflict_policy": "",
                "missing_decision_policy": "",
            },
            "assumptions": {
                "assumptions_in_force": [],
            },
        },
        "plan": {"content": ""},
        "state": documents["state"],
    }
    assert documents["state"]["phase"] == "planning"
    assert documents["state"]["brief_generation_status"] == "missing"


def test_update_task_partially_merges_fields(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    storage.node_store.save_task(
        project_id,
        root_id,
        {
            "title": "Alpha",
            "purpose": "Ship phase 4",
            "responsibility": "Own rollout",
        },
    )

    task = node_service.update_task(project_id, root_id, {"title": "Renamed Root"})

    assert task == {
        "title": "Renamed Root",
        "purpose": "Ship phase 4",
        "responsibility": "Own rollout",
    }


def test_update_briefing_is_blocked(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    with pytest.raises(NodeUpdateNotAllowed, match="Brief is locked"):
        node_service.update_briefing(
            project_id,
            root_id,
            {
                "node_snapshot": "Business context",
            },
        )


def test_update_spec_partially_merges_fields(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    spec = node_service.update_spec(
        project_id,
        root_id,
        {
            "mission": {
                "goal": "Do this",
                "success_outcome": "Ship the work",
            },
            "assumptions": {
                "assumptions_in_force": ["Assume that"],
            },
        },
    )

    assert spec["mission"]["goal"] == "Do this"
    assert spec["mission"]["success_outcome"] == "Ship the work"
    assert spec["assumptions"]["assumptions_in_force"] == ["Assume that"]
    assert spec["constraints"]["change_budget"] == ""


@pytest.mark.parametrize("updates", [{}, {"title": "   "}])
def test_update_task_rejects_empty_payload_or_blank_title(
    project_service: ProjectService,
    node_service: NodeService,
    workspace_root,
    updates: dict[str, str],
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    with pytest.raises(InvalidRequest):
        node_service.update_task(project_id, root_id, updates)


@pytest.mark.parametrize("status_update", [{"node_kind": "superseded"}, {"status": "done"}])
def test_document_updates_reject_superseded_and_done_nodes(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
    status_update: dict[str, object],
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_node(storage, project_id, root_id, **status_update)

    with pytest.raises(NodeUpdateNotAllowed):
        node_service.update_task(project_id, root_id, {"title": "Blocked"})

    with pytest.raises(NodeUpdateNotAllowed):
        node_service.update_briefing(project_id, root_id, {"user_notes": "Blocked"})


def test_update_spec_rejects_executing_phase(
    project_service: ProjectService,
    node_service: NodeService,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    mark_node(storage, project_id, root_id, phase="executing")

    with pytest.raises(NodeUpdateNotAllowed, match="executing"):
        node_service.update_spec(
            project_id,
            root_id,
            {"constraints": {"change_budget": "Frozen"}},
        )
