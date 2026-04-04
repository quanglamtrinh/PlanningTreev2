from __future__ import annotations

from backend.conversation.domain.events import NODE_DETAIL_INVALIDATE, NODE_WORKFLOW_UPDATED, build_workflow_envelope
from backend.streaming.sse_broker import GlobalEventBroker


class WorkflowEventPublisher:
    def __init__(self, broker: GlobalEventBroker) -> None:
        self._broker = broker

    def publish_workflow_updated(
        self,
        *,
        project_id: str,
        node_id: str,
        execution_state: str | None = None,
        review_state: str | None = None,
        workflow_phase: str | None = None,
        active_execution_run_id: str | None = None,
        active_review_cycle_id: str | None = None,
    ) -> dict:
        envelope = build_workflow_envelope(
            project_id=project_id,
            node_id=node_id,
            event_type=NODE_WORKFLOW_UPDATED,
            payload={
                "projectId": project_id,
                "nodeId": node_id,
                "executionState": execution_state,
                "reviewState": review_state,
                "workflowPhase": workflow_phase,
                "activeExecutionRunId": active_execution_run_id,
                "activeReviewCycleId": active_review_cycle_id,
            },
        )
        self._broker.publish(envelope)
        return envelope

    def publish_detail_invalidate(self, *, project_id: str, node_id: str, reason: str) -> dict:
        envelope = build_workflow_envelope(
            project_id=project_id,
            node_id=node_id,
            event_type=NODE_DETAIL_INVALIDATE,
            payload={
                "projectId": project_id,
                "nodeId": node_id,
                "reason": reason,
            },
        )
        self._broker.publish(envelope)
        return envelope
