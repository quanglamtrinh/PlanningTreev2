from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.execution_audit_orchestrator import ExecutionAuditOrchestratorV2
from backend.business.workflow_v2.legacy_v3_adapter import LegacyWorkflowV3CompatibilityAdapter
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.services import planningtree_workspace
from backend.tests.conftest import init_git_repo


class FakeSessionManager:
    def __init__(self) -> None:
        self.starts: list[dict[str, Any]] = []
        self.injects: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.starts.append(dict(payload or {}))
        return {"thread": {"id": f"thread-{len(self.starts)}"}}

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.injects.append({"threadId": thread_id, "payload": dict(payload)})
        return {"accepted": True}

    def turn_start(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.turns.append({"threadId": thread_id, "payload": dict(payload)})
        return {"turn": {"id": f"turn-{len(self.turns)}", "status": "inProgress"}}


def _project_with_confirmed_docs(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    init_git_repo(workspace_root)
    response = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    public_snapshot = response.json()
    project_id = public_snapshot["project"]["id"]
    node_id = public_snapshot["tree_state"]["root_node_id"]
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.md").write_text("Frame v1", encoding="utf-8")
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": 1,
                "confirmed_revision": 1,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": "Frame v1",
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text("Spec v1", encoding="utf-8")
    (node_dir / "spec.meta.json").write_text(
        json.dumps({"source_frame_revision": 1, "confirmed_at": "2026-04-24T00:00:00Z"}),
        encoding="utf-8",
    )
    return project_id, node_id


def _install_phase5_orchestrator(client: TestClient, manager: FakeSessionManager) -> ExecutionAuditOrchestratorV2:
    app = client.app
    event_publisher = WorkflowEventPublisherV2(app.state.workflow_event_broker)
    binding_service = ThreadBindingServiceV2(
        repository=app.state.workflow_state_repository_v2,
        context_builder=app.state.workflow_context_builder_v2,
        session_manager=manager,
        event_publisher=event_publisher,
    )
    orchestrator = ExecutionAuditOrchestratorV2(
        repository=app.state.workflow_state_repository_v2,
        thread_binding_service=binding_service,
        session_manager=manager,
        event_publisher=event_publisher,
        storage=app.state.storage,
        tree_service=app.state.tree_service,
        finish_task_service=app.state.finish_task_service,
        review_service=app.state.review_service,
        git_checkpoint_service=None,
    )
    app.state.workflow_thread_binding_service_v2 = binding_service
    app.state.execution_audit_orchestrator_v2 = orchestrator
    app.state.workflow_v3_compat_adapter = LegacyWorkflowV3CompatibilityAdapter(
        orchestrator=orchestrator,
        storage=app.state.storage,
        legacy_event_publisher=app.state.workflow_event_publisher,
    )
    app.state.execution_audit_workflow_service._workflow_orchestrator_v2 = orchestrator
    return orchestrator


def test_v4_execution_start_uses_v2_orchestrator_and_is_idempotent(client: TestClient, workspace_root: Path) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    _install_phase5_orchestrator(client, manager)

    payload = {"idempotencyKey": "exec-start-1", "model": "gpt-5.4", "modelProvider": "openai"}
    first = client.post(f"/v4/projects/{project_id}/nodes/{node_id}/execution/start", json=payload)
    second = client.post(f"/v4/projects/{project_id}/nodes/{node_id}/execution/start", json=payload)

    assert first.status_code == 200, first.json()
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["accepted"] is True
    assert first_payload["executionRunId"] == second_payload["executionRunId"]
    assert first_payload["workflowState"]["phase"] == "executing"
    assert first_payload["workflowState"]["threads"]["execution"] == "thread-1"
    assert len(manager.starts) == 1
    assert len(manager.injects) == 1
    assert len(manager.turns) == 1

    conflict = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={**payload, "model": "gpt-5.5"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ERR_WORKFLOW_IDEMPOTENCY_CONFLICT"

    invalid_phase = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-2"},
    )
    assert invalid_phase.status_code == 409
    assert invalid_phase.json()["code"] == "ERR_WORKFLOW_ACTION_NOT_ALLOWED"
    assert len(manager.turns) == 1


def test_session_turn_completion_observer_settles_execution_turn(client: TestClient, workspace_root: Path) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    orchestrator = _install_phase5_orchestrator(client, manager)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-settle"},
    )
    assert start.status_code == 200, start.json()
    start_payload = start.json()

    client.app.state.session_runtime_store_v2.create_turn(
        thread_id=start_payload["threadId"],
        turn_id=start_payload["turnId"],
        status="inProgress",
    )
    client.app.state.session_runtime_store_v2.append_notification(
        method="turn/completed",
        params={
            "threadId": start_payload["threadId"],
            "turn": {
                "id": start_payload["turnId"],
                "status": "completed",
                "items": [{"type": "agentMessage", "text": "Implemented the requested task."}],
            },
        },
    )

    workflow_state = orchestrator.get_workflow_state(project_id, node_id)

    assert workflow_state["phase"] == "execution_completed"
    assert workflow_state["decisions"]["execution"]["summaryText"] == "Implemented the requested task."


def test_v2_orchestrator_direct_settlement_is_idempotent_when_no_active_run(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    orchestrator = _install_phase5_orchestrator(client, manager)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-direct-settle"},
    )
    assert start.status_code == 200, start.json()
    start_payload = start.json()

    settled = orchestrator.settle_terminal_turn(
        thread_id=start_payload["threadId"],
        turn_id=start_payload["turnId"],
        status="completed",
        turn={
            "status": "completed",
            "items": [{"type": "agentMessage", "text": "Implemented the requested task."}],
        },
    )

    assert settled is not None
    workflow_state = settled["workflowState"]
    assert workflow_state["phase"] == "execution_completed"
    assert workflow_state["decisions"]["execution"]["summaryText"] == "Implemented the requested task."
    assert orchestrator.settle_terminal_turn(
        thread_id=start_payload["threadId"],
        turn_id=start_payload["turnId"],
        status="completed",
    ) is None


def test_v3_finish_task_delegates_to_attached_v2_orchestrator(client: TestClient, workspace_root: Path) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    _install_phase5_orchestrator(client, manager)

    response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task",
        json={"idempotencyKey": "legacy-finish-1"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["workflowPhase"] == "execution_running"
    assert payload["data"]["threadId"] == "thread-1"
    assert len(manager.turns) == 1


def test_v3_finish_task_replay_while_v2_execution_running_returns_active_run(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    _install_phase5_orchestrator(client, manager)

    first = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task",
        json={"idempotencyKey": "legacy-finish-1"},
    )
    second = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task",
        json={"idempotencyKey": "legacy-finish-2"},
    )

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    first_payload = first.json()["data"]
    second_payload = second.json()["data"]
    assert second_payload["workflowPhase"] == "execution_running"
    assert second_payload["executionRunId"] == first_payload["executionRunId"]
    assert second_payload["threadId"] == first_payload["threadId"]
    assert second_payload["turnId"] == first_payload["turnId"]
    assert len(manager.turns) == 1
