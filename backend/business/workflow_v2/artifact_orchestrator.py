from __future__ import annotations

from backend.business.workflow_v2.errors import WorkflowV2NotImplementedError


class ArtifactOrchestratorV2:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._args = args
        self._kwargs = kwargs

    def start_frame_generation(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("artifact_orchestrator.start_frame_generation")

    def start_spec_generation(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("artifact_orchestrator.start_spec_generation")

    def start_clarify(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("artifact_orchestrator.start_clarify")

    def start_split(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("artifact_orchestrator.start_split")

