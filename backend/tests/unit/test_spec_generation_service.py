from __future__ import annotations

import json

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import SpecGenerationInvalidResponse, SpecGenerationNotAllowed
from backend.services.project_service import ProjectService
from backend.services.spec_generation_service import SpecGenerationService
from backend.storage.storage import Storage


class FakeCodexClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
        on_tool_call=None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "prompt": prompt,
                "thread_id": thread_id,
                "timeout_sec": timeout_sec,
                "cwd": cwd,
                "writable_roots": list(writable_roots or []),
            }
        )
        if not self.outcomes:
            raise AssertionError("No fake outcomes remaining")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, dict):
            stdout = json.dumps(outcome)
        else:
            stdout = str(outcome)
        return {
            "stdout": stdout,
            "thread_id": thread_id or f"spec_thread_{len(self.calls)}",
        }


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def set_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = phase
    storage.project_store.save_snapshot(project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def build_service(storage: Storage, node_service, client: FakeCodexClient) -> SpecGenerationService:
    return SpecGenerationService(storage, client, node_service)


def make_spec(**overrides: object) -> dict[str, object]:
    spec = {
        "mission": {
            "goal": "Ship phase 5",
            "success_outcome": "Deliver the requested node output.",
            "implementation_level": "working",
        },
        "scope": {
            "must_do": ["Deliver the requested output"],
            "must_not_do": [],
            "deferred_work": [],
        },
        "constraints": {
            "hard_constraints": [],
            "change_budget": "Keep edits scoped to this node.",
            "touch_boundaries": [],
            "external_dependencies": [],
        },
        "autonomy": {
            "allowed_decisions": [],
            "requires_confirmation": [],
            "default_policy_when_unclear": "ask_user",
        },
        "verification": {
            "acceptance_checks": ["Output matches requested outcome"],
            "definition_of_done": "Node outcome is complete.",
            "evidence_expected": [],
        },
        "execution_controls": {
            "quality_profile": "standard",
            "tooling_limits": [],
            "output_expectation": "concise progress updates",
            "conflict_policy": "reopen_spec",
            "missing_decision_policy": "reopen_spec",
        },
        "assumptions": {
            "assumptions_in_force": [],
        },
    }
    spec.update(overrides)
    return spec


def test_generate_spec_retries_then_replaces_full_spec_and_marks_idle(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    storage.node_store.save_spec(
        project_id,
        root_id,
        make_spec(
            mission={
                "goal": "Old business",
                "success_outcome": "Old acceptance",
                "implementation_level": "working",
            },
            assumptions={"assumptions_in_force": ["Old assumptions"]},
        ),
    )
    client = FakeCodexClient(
        [
            "not json",
            make_spec(
                mission={
                    "goal": "New business",
                    "success_outcome": "New acceptance",
                    "implementation_level": "working",
                },
                constraints={
                    "hard_constraints": ["New technical"],
                    "change_budget": "Keep edits scoped to this node.",
                    "touch_boundaries": [],
                    "external_dependencies": [],
                },
                assumptions={"assumptions_in_force": ["New assumptions"]},
            ),
        ]
    )
    service = build_service(storage, node_service, client)

    response = service.generate_spec(project_id, root_id)

    assert response["spec"]["mission"]["goal"] == "New business"
    assert response["spec"]["mission"]["success_outcome"] == "New acceptance"
    assert response["spec"]["constraints"]["hard_constraints"] == ["New technical"]
    assert response["spec"]["assumptions"]["assumptions_in_force"] == ["New assumptions"]
    assert response["state"]["spec_generated"] is True
    assert response["state"]["spec_generation_status"] == "idle"
    assert response["state"]["phase"] == "spec_review"
    assert storage.node_store.load_spec(project_id, root_id) == response["spec"]
    assert len(client.calls) == 2


def test_generate_spec_from_ready_for_execution_steps_back_to_spec_review(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    node_service.update_spec(
        project_id,
        root_id,
        {
            "mission": {
                "goal": "Initial",
                "success_outcome": "Initial outcome",
                "implementation_level": "working",
            },
            "scope": {
                "must_do": ["Initial delivery"],
            },
            "autonomy": {
                "default_policy_when_unclear": "ask_user",
            },
        },
    )
    node_service.confirm_spec(project_id, root_id)
    client = FakeCodexClient(
        [
            make_spec(
                mission={
                    "goal": "Regenerated business",
                    "success_outcome": "Regenerated acceptance",
                    "implementation_level": "working",
                },
                constraints={
                    "hard_constraints": ["Regenerated technical"],
                    "change_budget": "Keep edits scoped to this node.",
                    "touch_boundaries": [],
                    "external_dependencies": [],
                },
                assumptions={"assumptions_in_force": ["Regenerated assumptions"]},
            )
        ]
    )
    service = build_service(storage, node_service, client)

    response = service.generate_spec(project_id, root_id)

    assert response["state"]["phase"] == "spec_review"
    assert response["state"]["spec_confirmed"] is False
    assert response["state"]["spec_generation_status"] == "idle"


@pytest.mark.parametrize("phase", ["planning", "briefing_review", "executing", "closed"])
def test_generate_spec_rejects_invalid_phases(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
    phase: str,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    set_phase(storage, project_id, root_id, phase)
    client = FakeCodexClient([])
    service = build_service(storage, node_service, client)

    with pytest.raises(SpecGenerationNotAllowed, match="spec_review"):
        service.generate_spec(project_id, root_id)


def test_generate_spec_rejects_non_mutable_and_planning_active_states(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["node_kind"] = "superseded"
    storage.project_store.save_snapshot(project_id, snapshot)
    client = FakeCodexClient([])
    service = build_service(storage, node_service, client)

    with pytest.raises(SpecGenerationNotAllowed, match="non-mutable"):
        service.generate_spec(project_id, root_id)

    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["node_kind"] = "root"
    storage.project_store.save_snapshot(project_id, snapshot)
    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        status="active",
        active_turn_id="planturn_1",
    )

    with pytest.raises(SpecGenerationNotAllowed, match="planning is active"):
        service.generate_spec(project_id, root_id)


def test_generate_spec_rejects_when_generation_already_active(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    state = storage.node_store.load_state(project_id, root_id)
    state["spec_generation_status"] = "generating"
    storage.node_store.save_state(project_id, root_id, state)
    service = build_service(storage, node_service, FakeCodexClient([]))

    with pytest.raises(SpecGenerationNotAllowed, match="already active"):
        service.generate_spec(project_id, root_id)


def test_generate_spec_invalid_output_marks_failed_and_keeps_existing_spec(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    existing_spec = make_spec(
        mission={
            "goal": "Keep business",
            "success_outcome": "Keep acceptance",
            "implementation_level": "working",
        },
        constraints={
            "hard_constraints": ["Keep technical"],
            "change_budget": "Keep edits scoped to this node.",
            "touch_boundaries": [],
            "external_dependencies": [],
        },
        assumptions={"assumptions_in_force": ["Keep assumptions"]},
    )
    storage.node_store.save_spec(project_id, root_id, existing_spec)
    client = FakeCodexClient(["still bad", "also bad"])
    service = build_service(storage, node_service, client)

    with pytest.raises(SpecGenerationInvalidResponse):
        service.generate_spec(project_id, root_id)

    state = storage.node_store.load_state(project_id, root_id)
    assert state["spec_generation_status"] == "failed"
    assert storage.node_store.load_spec(project_id, root_id) == existing_spec


def test_generate_spec_transport_error_marks_failed(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    node_service.confirm_task(project_id, root_id)
    node_service.confirm_briefing(project_id, root_id)
    service = build_service(
        storage,
        node_service,
        FakeCodexClient([CodexTransportError("boom", "rpc_error")]),
    )

    with pytest.raises(CodexTransportError, match="boom"):
        service.generate_spec(project_id, root_id)

    state = storage.node_store.load_state(project_id, root_id)
    assert state["spec_generation_status"] == "failed"


def test_reconcile_interrupted_generations_marks_generating_as_failed(
    project_service: ProjectService,
    node_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    state = storage.node_store.load_state(project_id, root_id)
    state["spec_generation_status"] = "generating"
    storage.node_store.save_state(project_id, root_id, state)
    service = build_service(storage, node_service, FakeCodexClient([]))

    service.reconcile_interrupted_generations()

    recovered = storage.node_store.load_state(project_id, root_id)
    assert recovered["spec_generation_status"] == "failed"
