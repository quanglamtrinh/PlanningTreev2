from __future__ import annotations

from backend.business.workflow_v2.context_packets import PlanningTreeContextPacket
from backend.business.workflow_v2.errors import WorkflowV2NotImplementedError
from backend.business.workflow_v2.models import ThreadRole


class WorkflowContextBuilderV2:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._args = args
        self._kwargs = kwargs

    def build_context_packet(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
    ) -> PlanningTreeContextPacket:
        raise WorkflowV2NotImplementedError("context_builder.build_context_packet")

