from __future__ import annotations

import copy
import logging
import os
from typing import Any, Literal

from backend.business.workflow_v2.errors import WorkflowActionNotAllowedError, WorkflowV2Error

WorkflowV3CompatMode = Literal["adapter", "read_only", "off"]

WORKFLOW_V3_DEPRECATION_HEADERS = {
    "Deprecation": "true",
    "X-PlanningTree-Deprecated-Surface": "workflow-v3",
    "X-PlanningTree-Replacement-Surface": "workflow-v2",
}

logger = logging.getLogger(__name__)


class LegacyWorkflowV3CompatibilityAdapter:
    """Compatibility facade for legacy V3 workflow routes.

    The adapter preserves the old V3 response payloads while delegating all
    workflow decisions and persistence to Workflow Core V2.
    """

    def __init__(
        self,
        *,
        orchestrator: Any,
        storage: Any | None = None,
        legacy_event_publisher: Any | None = None,
        mode: str | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._storage = storage
        self._legacy_event_publisher = legacy_event_publisher
        self.mode: WorkflowV3CompatMode = _normalize_mode(
            mode if mode is not None else os.environ.get("WORKFLOW_V3_COMPAT_MODE")
        )
        self.telemetry_events: list[dict[str, Any]] = []

    def get_workflow_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        self._record("workflow-state", project_id, node_id, mutating=False)
        self._ensure_read_allowed()
        return self._legacy_state(project_id, node_id)

    def finish_task(self, project_id: str, node_id: str, *, idempotency_key: str) -> dict[str, Any]:
        self._record("workflow/finish-task", project_id, node_id, mutating=True)
        self._ensure_mutation_allowed("finish-task")
        refresh_reason = "finish_task_started"
        try:
            response = self._orchestrator.start_execution(
                project_id,
                node_id,
                idempotency_key=idempotency_key,
            )
        except WorkflowActionNotAllowedError as exc:
            if exc.details.get("action") != "start_execution" or exc.details.get("phase") != "executing":
                raise
            active_response = self._orchestrator.get_active_execution_start_response(project_id, node_id)
            if active_response is None:
                raise
            response = active_response
            refresh_reason = "finish_task_already_executing"
        state = self._legacy_state(project_id, node_id)
        self._publish_legacy_refresh(project_id, node_id, refresh_reason)
        return {
            "accepted": True,
            "threadId": response.get("threadId"),
            "turnId": response.get("turnId"),
            "executionRunId": response.get("executionRunId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def mark_done_from_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        self._record("workflow/mark-done-from-execution", project_id, node_id, mutating=True)
        self._ensure_mutation_allowed("mark-done-from-execution")
        self._orchestrator.mark_done_from_execution(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_workspace_hash=expected_workspace_hash,
        )
        self._publish_legacy_refresh(project_id, node_id, "mark_done_from_execution")
        return self._legacy_state(project_id, node_id)

    def review_in_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_workspace_hash: str,
    ) -> dict[str, Any]:
        self._record("workflow/review-in-audit", project_id, node_id, mutating=True)
        self._ensure_mutation_allowed("review-in-audit")
        response = self._orchestrator.start_audit(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_workspace_hash=expected_workspace_hash,
        )
        state = self._legacy_state(project_id, node_id)
        self._publish_legacy_refresh(project_id, node_id, "review_in_audit_started")
        return {
            "accepted": True,
            "reviewCycleId": response.get("auditRunId") or response.get("reviewCycleId"),
            "reviewThreadId": response.get("reviewThreadId") or response.get("threadId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def improve_in_execution(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        self._record("workflow/improve-in-execution", project_id, node_id, mutating=True)
        self._ensure_mutation_allowed("improve-in-execution")
        response = self._orchestrator.request_improvements(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_review_commit_sha=expected_review_commit_sha,
        )
        state = self._legacy_state(project_id, node_id)
        self._publish_legacy_refresh(project_id, node_id, "improve_in_execution_started")
        return {
            "accepted": True,
            "threadId": response.get("threadId"),
            "turnId": response.get("turnId"),
            "executionRunId": response.get("executionRunId"),
            "workflowPhase": state.get("workflowPhase"),
        }

    def mark_done_from_audit(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
        expected_review_commit_sha: str,
    ) -> dict[str, Any]:
        self._record("workflow/mark-done-from-audit", project_id, node_id, mutating=True)
        self._ensure_mutation_allowed("mark-done-from-audit")
        self._orchestrator.accept_audit(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            expected_review_commit_sha=expected_review_commit_sha,
        )
        self._publish_legacy_refresh(project_id, node_id, "mark_done_from_audit")
        return self._legacy_state(project_id, node_id)

    def project_legacy_workflow_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(event.get("type") or event.get("eventType") or "").strip()
        if event_type not in {"workflow/state_changed", "workflow/action_completed"}:
            return None
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        return {
            "type": "node.workflow.updated",
            "projectId": event.get("projectId"),
            "nodeId": event.get("nodeId"),
            "eventId": event.get("eventId"),
            "workflowPhase": details.get("phase") or details.get("workflowPhase"),
            "activeExecutionRunId": details.get("activeExecutionRunId"),
            "activeReviewCycleId": details.get("activeAuditRunId") or details.get("activeReviewCycleId"),
        }

    def _legacy_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        state = copy.deepcopy(self._orchestrator.get_legacy_workflow_state(project_id, node_id))
        self._hydrate_legacy_thread_ids(project_id, node_id, state)
        return state

    def _hydrate_legacy_thread_ids(self, project_id: str, node_id: str, state: dict[str, Any]) -> None:
        if self._storage is None:
            return
        ask_thread_id = self._registry_thread_id(project_id, node_id, "ask_planning")
        execution_thread_id = self._registry_thread_id(project_id, node_id, "execution")
        audit_thread_id = self._registry_thread_id(project_id, node_id, "audit")
        if ask_thread_id and state.get("askThreadId") != ask_thread_id:
            state["askThreadId"] = ask_thread_id
        if not state.get("executionThreadId") and execution_thread_id:
            state["executionThreadId"] = execution_thread_id
        if not state.get("auditLineageThreadId") and audit_thread_id:
            state["auditLineageThreadId"] = audit_thread_id
        if not state.get("reviewThreadId") and audit_thread_id:
            state["reviewThreadId"] = audit_thread_id

    def _registry_thread_id(self, project_id: str, node_id: str, role: str) -> str | None:
        registry = getattr(self._storage, "thread_registry_store", None)
        if registry is None:
            return None
        try:
            entry = registry.read_entry(project_id, node_id, role)
        except Exception:
            logger.debug("Failed to read legacy workflow thread registry entry", exc_info=True)
            return None
        if not isinstance(entry, dict):
            return None
        thread_id = str(entry.get("threadId") or "").strip()
        return thread_id or None

    def _publish_legacy_refresh(self, project_id: str, node_id: str, reason: str) -> None:
        # Workflow V2 already publishes native events. This best-effort call
        # preserves legacy project-event listeners while they are being retired.
        publisher = self._legacy_event_publisher
        if publisher is None:
            return
        try:
            state = self._legacy_state(project_id, node_id)
            publisher.publish_workflow_updated(
                project_id=project_id,
                node_id=node_id,
                execution_state=None,
                review_state=None,
                workflow_phase=str(state.get("workflowPhase") or "") or None,
                active_execution_run_id=str(state.get("activeExecutionRunId") or "") or None,
                active_review_cycle_id=str(state.get("activeReviewCycleId") or "") or None,
            )
            publisher.publish_detail_invalidate(project_id=project_id, node_id=node_id, reason=reason)
        except Exception:
            logger.debug("Failed to publish legacy workflow refresh", exc_info=True)

    def _ensure_read_allowed(self) -> None:
        if self.mode == "off":
            raise WorkflowV2Error(
                "ERR_WORKFLOW_V3_DEPRECATED",
                "Workflow V3 compatibility routes are disabled. Use Workflow V2.",
                status_code=410,
                details={"surface": "workflow-v3", "replacement": "workflow-v2", "mode": self.mode},
            )

    def _ensure_mutation_allowed(self, action: str) -> None:
        self._ensure_read_allowed()
        if self.mode == "read_only":
            raise WorkflowV2Error(
                "ERR_WORKFLOW_V3_DEPRECATED",
                "Workflow V3 mutations are deprecated. Use Workflow V2.",
                status_code=410,
                details={
                    "surface": "workflow-v3",
                    "replacement": "workflow-v2",
                    "mode": self.mode,
                    "action": action,
                },
            )

    def _record(self, route: str, project_id: str, node_id: str, *, mutating: bool) -> None:
        event = {
            "surface": "workflow-v3",
            "replacement": "workflow-v2",
            "route": route,
            "projectId": project_id,
            "nodeId": node_id,
            "mutating": mutating,
            "mode": self.mode,
        }
        self.telemetry_events.append(event)
        logger.info("workflow_v3_compat_route", extra=event)


def _normalize_mode(value: str | None) -> WorkflowV3CompatMode:
    normalized = str(value or "adapter").strip().lower().replace("-", "_")
    if normalized in {"adapter", "read_only", "off"}:
        return normalized  # type: ignore[return-value]
    return "adapter"
