from __future__ import annotations

import pytest

from backend.business.workflow_v2.errors import WorkflowActionNotAllowedError, WorkflowV2Error
from backend.business.workflow_v2.legacy_v3_adapter import (
    WORKFLOW_V3_DEPRECATION_HEADERS,
    LegacyWorkflowV3CompatibilityAdapter,
)


class _FakeThreadRegistry:
    def __init__(self) -> None:
        self.entries = {
            "ask_planning": {"threadId": "ask-thread"},
            "execution": {"threadId": "execution-thread"},
            "audit": {"threadId": "audit-thread"},
        }

    def read_entry(self, _project_id: str, _node_id: str, role: str) -> dict:
        return dict(self.entries.get(role, {}))


class _FakeStorage:
    def __init__(self) -> None:
        self.thread_registry_store = _FakeThreadRegistry()


class _FakeLegacyPublisher:
    def __init__(self) -> None:
        self.workflow_updates: list[dict] = []
        self.invalidations: list[dict] = []

    def publish_workflow_updated(self, **kwargs) -> dict:
        self.workflow_updates.append(dict(kwargs))
        return dict(kwargs)

    def publish_detail_invalidate(self, **kwargs) -> dict:
        self.invalidations.append(dict(kwargs))
        return dict(kwargs)


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.active_start_response = {
            "threadId": "execution-thread",
            "turnId": "turn-active",
            "executionRunId": "run-active",
        }
        self.raise_already_executing = False
        self.legacy_state = {
            "workflowPhase": "idle",
            "askThreadId": None,
            "executionThreadId": None,
            "auditLineageThreadId": None,
            "reviewThreadId": None,
            "activeExecutionRunId": None,
            "latestExecutionRunId": None,
            "activeReviewCycleId": None,
            "latestReviewCycleId": None,
            "currentExecutionDecision": None,
            "currentAuditDecision": None,
            "acceptedSha": None,
            "runtimeBlock": None,
            "canSendExecutionMessage": False,
            "canReviewInAudit": False,
            "canImproveInExecution": False,
            "canMarkDoneFromExecution": False,
            "canMarkDoneFromAudit": False,
        }

    def get_legacy_workflow_state(self, project_id: str, node_id: str) -> dict:
        self.calls.append(("get_legacy_workflow_state", {"projectId": project_id, "nodeId": node_id}))
        return dict(self.legacy_state)

    def start_execution(self, project_id: str, node_id: str, *, idempotency_key: str) -> dict:
        self.calls.append(("start_execution", {"projectId": project_id, "nodeId": node_id, "key": idempotency_key}))
        if self.raise_already_executing:
            raise WorkflowActionNotAllowedError("start_execution", "executing")
        self.legacy_state["workflowPhase"] = "executing"
        self.legacy_state["activeExecutionRunId"] = "run-1"
        return {"threadId": "execution-thread", "turnId": "turn-1", "executionRunId": "run-1"}

    def get_active_execution_start_response(self, project_id: str, node_id: str) -> dict:
        self.calls.append(("get_active_execution_start_response", {"projectId": project_id, "nodeId": node_id}))
        self.legacy_state["workflowPhase"] = "executing"
        self.legacy_state["activeExecutionRunId"] = "run-active"
        return dict(self.active_start_response)

    def mark_done_from_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> None:
        self.calls.append(
            (
                "mark_done_from_execution",
                {
                    "projectId": project_id,
                    "nodeId": node_id,
                    "key": idempotency_key,
                    "expectedWorkspaceHash": expected_workspace_hash,
                },
            )
        )
        self.legacy_state["workflowPhase"] = "done"

    def start_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict:
        self.calls.append(
            (
                "start_audit",
                {
                    "projectId": project_id,
                    "nodeId": node_id,
                    "key": idempotency_key,
                    "expectedWorkspaceHash": expected_workspace_hash,
                },
            )
        )
        self.legacy_state["workflowPhase"] = "auditing"
        self.legacy_state["activeReviewCycleId"] = "audit-1"
        return {"auditRunId": "audit-1", "threadId": "audit-thread"}

    def request_improvements(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict:
        self.calls.append(
            (
                "request_improvements",
                {
                    "projectId": project_id,
                    "nodeId": node_id,
                    "key": idempotency_key,
                    "expectedReviewCommitSha": expected_review_commit_sha,
                },
            )
        )
        self.legacy_state["workflowPhase"] = "executing"
        self.legacy_state["activeExecutionRunId"] = "run-2"
        return {"threadId": "execution-thread", "turnId": "turn-2", "executionRunId": "run-2"}

    def accept_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> None:
        self.calls.append(
            (
                "accept_audit",
                {
                    "projectId": project_id,
                    "nodeId": node_id,
                    "key": idempotency_key,
                    "expectedReviewCommitSha": expected_review_commit_sha,
                },
            )
        )
        self.legacy_state["workflowPhase"] = "done"


def _adapter(
    orchestrator: _FakeOrchestrator | None = None,
    *,
    mode: str | None = None,
) -> tuple[LegacyWorkflowV3CompatibilityAdapter, _FakeOrchestrator, _FakeLegacyPublisher]:
    resolved_orchestrator = orchestrator or _FakeOrchestrator()
    publisher = _FakeLegacyPublisher()
    return (
        LegacyWorkflowV3CompatibilityAdapter(
            orchestrator=resolved_orchestrator,
            storage=_FakeStorage(),
            legacy_event_publisher=publisher,
            mode=mode,
        ),
        resolved_orchestrator,
        publisher,
    )


def test_legacy_state_is_sourced_from_v2_and_hydrates_legacy_thread_ids() -> None:
    adapter, orchestrator, _publisher = _adapter()

    state = adapter.get_workflow_state("project-1", "node-1")

    assert state["workflowPhase"] == "idle"
    assert state["askThreadId"] == "ask-thread"
    assert state["executionThreadId"] == "execution-thread"
    assert state["auditLineageThreadId"] == "audit-thread"
    assert state["reviewThreadId"] == "audit-thread"
    assert orchestrator.calls[0][0] == "get_legacy_workflow_state"
    assert adapter.telemetry_events[-1]["route"] == "workflow-state"
    assert adapter.telemetry_events[-1]["replacement"] == "workflow-v2"


def test_v3_finish_task_delegates_to_start_execution_and_preserves_legacy_shape() -> None:
    adapter, _orchestrator, publisher = _adapter()

    payload = adapter.finish_task("project-1", "node-1", idempotency_key="idem-1")

    assert payload == {
        "accepted": True,
        "threadId": "execution-thread",
        "turnId": "turn-1",
        "executionRunId": "run-1",
        "workflowPhase": "executing",
    }
    assert publisher.workflow_updates[-1]["workflow_phase"] == "executing"
    assert publisher.invalidations[-1]["reason"] == "finish_task_started"


def test_v3_finish_task_replays_active_execution_when_v2_reports_already_executing() -> None:
    orchestrator = _FakeOrchestrator()
    orchestrator.raise_already_executing = True
    adapter, orchestrator, publisher = _adapter(orchestrator)

    payload = adapter.finish_task("project-1", "node-1", idempotency_key="idem-1")

    assert payload["turnId"] == "turn-active"
    assert payload["executionRunId"] == "run-active"
    assert ("get_active_execution_start_response", {"projectId": "project-1", "nodeId": "node-1"}) in orchestrator.calls
    assert publisher.invalidations[-1]["reason"] == "finish_task_already_executing"


def test_v3_execution_and_audit_mutations_delegate_to_v2_orchestrator() -> None:
    adapter, orchestrator, _publisher = _adapter()

    assert adapter.mark_done_from_execution(
        "project-1",
        "node-1",
        idempotency_key="done-1",
        expected_workspace_hash="hash-1",
    )["workflowPhase"] == "done"
    review_payload = adapter.review_in_audit(
        "project-1",
        "node-1",
        idempotency_key="audit-1",
        expected_workspace_hash="hash-2",
    )
    improve_payload = adapter.improve_in_execution(
        "project-1",
        "node-1",
        idempotency_key="improve-1",
        expected_review_commit_sha="sha-1",
    )
    assert adapter.mark_done_from_audit(
        "project-1",
        "node-1",
        idempotency_key="accept-1",
        expected_review_commit_sha="sha-2",
    )["workflowPhase"] == "done"

    assert review_payload["accepted"] is True
    assert review_payload["reviewCycleId"] == "audit-1"
    assert improve_payload["accepted"] is True
    assert improve_payload["executionRunId"] == "run-2"
    assert [name for name, _payload in orchestrator.calls] == [
        "mark_done_from_execution",
        "get_legacy_workflow_state",
        "get_legacy_workflow_state",
        "start_audit",
        "get_legacy_workflow_state",
        "get_legacy_workflow_state",
        "request_improvements",
        "get_legacy_workflow_state",
        "get_legacy_workflow_state",
        "accept_audit",
        "get_legacy_workflow_state",
        "get_legacy_workflow_state",
    ]


def test_read_only_mode_blocks_v3_workflow_mutations_but_allows_reads() -> None:
    adapter, _orchestrator, _publisher = _adapter(mode="read_only")

    assert adapter.get_workflow_state("project-1", "node-1")["workflowPhase"] == "idle"

    with pytest.raises(WorkflowV2Error) as exc_info:
        adapter.finish_task("project-1", "node-1", idempotency_key="idem-1")

    assert exc_info.value.status_code == 410
    assert exc_info.value.code == "ERR_WORKFLOW_V3_DEPRECATED"
    assert exc_info.value.details["mode"] == "read_only"


def test_off_mode_blocks_v3_workflow_reads_and_mutations() -> None:
    adapter, _orchestrator, _publisher = _adapter(mode="off")

    with pytest.raises(WorkflowV2Error) as exc_info:
        adapter.get_workflow_state("project-1", "node-1")

    assert exc_info.value.status_code == 410
    assert exc_info.value.details["replacement"] == "workflow-v2"


def test_deprecation_headers_are_stable_for_v3_workflow_routes() -> None:
    assert WORKFLOW_V3_DEPRECATION_HEADERS == {
        "Deprecation": "true",
        "X-PlanningTree-Deprecated-Surface": "workflow-v3",
        "X-PlanningTree-Replacement-Surface": "workflow-v2",
    }
