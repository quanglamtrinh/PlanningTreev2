from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.business.workflow_v2.models import NodeWorkflowStateV2, WorkflowAction, WorkflowPhase
from backend.streaming.sse_broker import GlobalEventBroker

WorkflowEventType = Literal[
    "workflow/state_changed",
    "workflow/context_stale",
    "workflow/action_completed",
    "workflow/action_failed",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_event_id() -> str:
    return f"workflow_evt_{uuid4().hex[:12]}"


class WorkflowEventV2(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: WorkflowEventType
    project_id: str = Field(alias="projectId")
    node_id: str = Field(alias="nodeId")
    phase: WorkflowPhase | None = None
    version: int | None = None
    action: WorkflowAction | None = None
    event_id: str = Field(default_factory=_new_event_id, alias="eventId")
    occurred_at: str = Field(default_factory=_now_iso, alias="occurredAt")
    details: dict[str, Any] = Field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class WorkflowEventPublisherV2:
    def __init__(self, broker: GlobalEventBroker) -> None:
        self._broker = broker

    def publish_state_changed(
        self,
        state: NodeWorkflowStateV2,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._publish(
            WorkflowEventV2(
                type="workflow/state_changed",
                projectId=state.project_id,
                nodeId=state.node_id,
                phase=state.phase,
                version=state.state_version,
                details=details or {},
            )
        )

    def publish_context_stale(
        self,
        state: NodeWorkflowStateV2,
        *,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_details = dict(details or {})
        if reason:
            event_details["reason"] = reason
        return self._publish(
            WorkflowEventV2(
                type="workflow/context_stale",
                projectId=state.project_id,
                nodeId=state.node_id,
                phase=state.phase,
                version=state.state_version,
                details=event_details,
            )
        )

    def publish_action_completed(
        self,
        state: NodeWorkflowStateV2,
        *,
        action: WorkflowAction,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._publish(
            WorkflowEventV2(
                type="workflow/action_completed",
                projectId=state.project_id,
                nodeId=state.node_id,
                phase=state.phase,
                version=state.state_version,
                action=action,
                details=details or {},
            )
        )

    def publish_action_failed(
        self,
        state: NodeWorkflowStateV2,
        *,
        action: WorkflowAction,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._publish(
            WorkflowEventV2(
                type="workflow/action_failed",
                projectId=state.project_id,
                nodeId=state.node_id,
                phase=state.phase,
                version=state.state_version,
                action=action,
                details=details or {},
            )
        )

    def _publish(self, event: WorkflowEventV2) -> dict[str, Any]:
        payload = event.to_public_dict()
        self._broker.publish(payload)
        return payload
