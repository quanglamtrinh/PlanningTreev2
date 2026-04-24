from __future__ import annotations

from backend.business.workflow_v2.errors import WorkflowV2NotImplementedError


class ExecutionAuditOrchestratorV2:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._args = args
        self._kwargs = kwargs

    def start_execution(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.start_execution")

    def complete_execution(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.complete_execution")

    def mark_done_from_execution(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.mark_done_from_execution")

    def start_audit(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.start_audit")

    def accept_audit(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.accept_audit")

    def request_improvements(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.request_improvements")

    def start_package_review(self, *args: object, **kwargs: object) -> None:
        raise WorkflowV2NotImplementedError("execution_audit_orchestrator.start_package_review")

