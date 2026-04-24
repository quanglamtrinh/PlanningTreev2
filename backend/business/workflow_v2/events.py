from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.business.workflow_v2.models import WorkflowAction, WorkflowPhase

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

