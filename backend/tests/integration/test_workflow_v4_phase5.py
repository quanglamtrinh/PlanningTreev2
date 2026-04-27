from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.execution_audit_orchestrator import ExecutionAuditOrchestratorV2
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.services import planningtree_workspace
from backend.tests.conftest import init_git_repo


class FakeSessionManager:
    def __init__(self, *, turn_start_response: dict[str, Any] | None = None) -> None:
        self.starts: list[dict[str, Any]] = []
        self.injects: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []
        self.turn_start_response = (
            dict(turn_start_response)
            if isinstance(turn_start_response, dict)
            else None
        )

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.starts.append(dict(payload or {}))
        return {"thread": {"id": f"thread-{len(self.starts)}"}}

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.injects.append({"threadId": thread_id, "payload": dict(payload)})
        return {"accepted": True}

    def turn_start(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.turns.append({"threadId": thread_id, "payload": dict(payload)})
        if self.turn_start_response is not None:
            return dict(self.turn_start_response)
        return {"turn": {"id": f"turn-{len(self.turns)}", "status": "inProgress"}}


class RecoveringSessionManager(FakeSessionManager):
    def __init__(self, *, recovered_text: str) -> None:
        super().__init__()
        self.recovered_text = recovered_text
        self.recoveries: list[dict[str, Any]] = []
        self.completed_turns: dict[tuple[str, str], dict[str, Any]] = {}

    def thread_recover(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.recoveries.append({"threadId": thread_id, "payload": dict(payload)})
        for turn in self.turns:
            if turn["threadId"] != thread_id:
                continue
            response_turn_id = f"turn-{self.turns.index(turn) + 1}"
            self.completed_turns[(thread_id, response_turn_id)] = {
                "id": response_turn_id,
                "status": "completed",
                "items": [{"type": "agentMessage", "text": self.recovered_text}],
            }
        return {"thread": {"id": thread_id}, "recovered": {"terminalTurnCount": len(self.completed_turns)}}

    def get_runtime_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any] | None:
        turn = self.completed_turns.get((thread_id, turn_id))
        return dict(turn) if turn is not None else None


class FastCompletingSessionManager(FakeSessionManager):
    def __init__(self, *, completed_text: str) -> None:
        super().__init__()
        self.completed_text = completed_text
        self.completed_turns: dict[tuple[str, str], dict[str, Any]] = {}

    def turn_start(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = super().turn_start(thread_id=thread_id, payload=payload)
        turn = response.get("turn") if isinstance(response, dict) else None
        turn_id = str(turn.get("id") or "" if isinstance(turn, dict) else "").strip()
        if turn_id:
            self.completed_turns[(thread_id, turn_id)] = {
                "id": turn_id,
                "status": "completed",
                "items": [{"type": "agentMessage", "text": self.completed_text}],
            }
        return response

    def get_runtime_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any] | None:
        turn = self.completed_turns.get((thread_id, turn_id))
        return dict(turn) if turn is not None else None


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


def _install_phase5_orchestrator(
    client: TestClient,
    manager: FakeSessionManager,
    *,
    use_git_checkpoint_service: bool = False,
) -> ExecutionAuditOrchestratorV2:
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
        git_checkpoint_service=app.state.git_checkpoint_service if use_git_checkpoint_service else None,
    )
    app.state.workflow_thread_binding_service_v2 = binding_service
    app.state.execution_audit_orchestrator_v2 = orchestrator
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


def test_execution_start_settles_fast_terminal_turn_after_state_write(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FastCompletingSessionManager(completed_text="Fast native completion.")
    orchestrator = _install_phase5_orchestrator(client, manager)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-fast-terminal"},
    )

    assert start.status_code == 200, start.json()
    start_payload = start.json()
    assert start_payload["workflowState"]["phase"] == "execution_completed"
    workflow_state = orchestrator.get_workflow_state(project_id, node_id)
    assert workflow_state["phase"] == "execution_completed"
    assert workflow_state["decisions"]["execution"]["summaryText"] == "Fast native completion."


def test_workflow_state_recovers_missed_execution_completion_from_provider(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = RecoveringSessionManager(recovered_text="Recovered execution summary.")
    _install_phase5_orchestrator(client, manager)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-recover"},
    )
    assert start.status_code == 200, start.json()

    state_response = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state")

    assert state_response.status_code == 200, state_response.json()
    workflow_state = state_response.json()
    assert manager.recoveries
    assert workflow_state["phase"] == "execution_completed"
    assert workflow_state["decisions"]["execution"]["summaryText"] == "Recovered execution summary."


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


def test_audit_settlement_uses_final_review_message_for_improve_prompt(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    orchestrator = _install_phase5_orchestrator(client, manager, use_git_checkpoint_service=True)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-before-audit-review"},
    )
    assert start.status_code == 200, start.json()
    start_payload = start.json()
    execution_settled = orchestrator.settle_terminal_turn(
        thread_id=start_payload["threadId"],
        turn_id=start_payload["turnId"],
        status="completed",
        turn={
            "status": "completed",
            "items": [{"type": "agentMessage", "text": "Implemented the requested task."}],
        },
    )
    assert execution_settled is not None
    workspace_hash = execution_settled["workflowState"]["decisions"]["execution"]["candidateWorkspaceHash"]

    audit = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/audit/start",
        json={"idempotencyKey": "audit-start-final-review-text", "expectedWorkspaceHash": workspace_hash},
    )
    assert audit.status_code == 200, audit.json()
    audit_payload = audit.json()
    final_review_summary = "Final review summary: please tighten the frame copy."
    audit_settled = orchestrator.settle_terminal_turn(
        thread_id=audit_payload["threadId"],
        turn_id=audit_payload["turnId"],
        status="completed",
        turn={
            "status": "completed",
            "items": [
                {
                    "type": "reasoning",
                    "summary": "Reasoning summary should never become the improve request.",
                },
                {"type": "agentMessage", "text": "Earlier audit note should not drive improve."},
                {
                    "type": "agentMessage",
                    "content": [{"type": "text", "text": final_review_summary}],
                },
            ],
        },
    )

    assert audit_settled is not None
    audit_decision = audit_settled["workflowState"]["decisions"]["audit"]
    assert audit_decision["finalReviewText"] == final_review_summary

    improve = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/improve",
        json={
            "idempotencyKey": "execution-improve-from-final-review-text",
            "expectedReviewCommitSha": audit_decision["reviewCommitSha"],
        },
    )

    assert improve.status_code == 200, improve.json()
    improve_prompt = manager.turns[-1]["payload"]["input"][0]["text"]
    assert final_review_summary in improve_prompt
    assert "Reasoning summary should never become the improve request." not in improve_prompt
    assert "Earlier audit note should not drive improve." not in improve_prompt


def test_improve_uses_runtime_turn_message_when_audit_decision_text_missing(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager()
    orchestrator = _install_phase5_orchestrator(client, manager, use_git_checkpoint_service=True)

    start = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-before-audit-fallback"},
    )
    assert start.status_code == 200, start.json()
    start_payload = start.json()
    execution_settled = orchestrator.settle_terminal_turn(
        thread_id=start_payload["threadId"],
        turn_id=start_payload["turnId"],
        status="completed",
        turn={
            "status": "completed",
            "items": [{"type": "agentMessage", "text": "Implemented the requested task."}],
        },
    )
    assert execution_settled is not None
    workspace_hash = execution_settled["workflowState"]["decisions"]["execution"]["candidateWorkspaceHash"]

    audit = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/audit/start",
        json={"idempotencyKey": "audit-start-review-text-fallback", "expectedWorkspaceHash": workspace_hash},
    )
    assert audit.status_code == 200, audit.json()
    audit_payload = audit.json()
    audit_settled = orchestrator.settle_terminal_turn(
        thread_id=audit_payload["threadId"],
        turn_id=audit_payload["turnId"],
        status="completed",
        turn={
            "status": "completed",
            "items": [
                {
                    "type": "reasoning",
                    "summary": "Reasoning summary should not become improve review text.",
                },
            ],
        },
    )
    assert audit_settled is not None
    audit_decision = audit_settled["workflowState"]["decisions"]["audit"]
    assert audit_decision["finalReviewText"] is None

    runtime_audit_text = "Please apply the requested fixes from this completed review message."

    def runtime_turn(*, thread_id: str, turn_id: str) -> dict[str, Any] | None:
        if thread_id != audit_payload["threadId"] or turn_id != audit_payload["turnId"]:
            return None
        return {
            "id": turn_id,
            "status": "completed",
            "items": [
                {
                    "type": "reasoning",
                    "summary": "Reasoning summary should not become improve review text.",
                },
                {
                    "type": "agentMessage",
                    "content": [{"type": "text", "text": runtime_audit_text}],
                },
            ],
        }

    manager.get_runtime_turn = runtime_turn  # type: ignore[attr-defined]

    improve = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/improve",
        json={
            "idempotencyKey": "execution-improve-runtime-turn-review-fallback",
            "expectedReviewCommitSha": audit_decision["reviewCommitSha"],
        },
    )

    assert improve.status_code == 200, improve.json()
    improve_prompt = manager.turns[-1]["payload"]["input"][0]["text"]
    assert runtime_audit_text in improve_prompt
    assert "Reasoning summary should not become improve review text." not in improve_prompt


def test_v4_execution_start_fails_when_session_turn_start_missing_turn_id(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)
    manager = FakeSessionManager(turn_start_response={"status": "accepted"})
    _install_phase5_orchestrator(client, manager)

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/execution/start",
        json={"idempotencyKey": "exec-start-missing-turn-id"},
    )

    assert response.status_code == 502, response.json()
    payload = response.json()
    assert payload["code"] == "ERR_INTERNAL"
    assert "missing turnId" in payload["message"]
    assert len(manager.turns) == 1

    workflow_state_response = client.get(
        f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state"
    )
    assert workflow_state_response.status_code == 200
    workflow_state_payload = workflow_state_response.json()
    assert workflow_state_payload["phase"] == "ready_for_execution"


