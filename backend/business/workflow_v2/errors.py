from __future__ import annotations

import copy
from typing import Any


class WorkflowV2Error(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = copy.deepcopy(details or {})

    def to_envelope(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": copy.deepcopy(self.details),
        }


class WorkflowNotFoundError(WorkflowV2Error):
    def __init__(self, project_id: str, node_id: str) -> None:
        super().__init__(
            "ERR_WORKFLOW_NOT_FOUND",
            f"Workflow state for node {node_id!r} was not found.",
            status_code=404,
            details={"projectId": project_id, "nodeId": node_id},
        )


class WorkflowActionNotAllowedError(WorkflowV2Error):
    def __init__(
        self,
        action: str,
        phase: str,
        *,
        allowed_actions: list[str] | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(
            "ERR_WORKFLOW_ACTION_NOT_ALLOWED",
            message or f"Workflow action {action!r} is not allowed in phase {phase!r}.",
            status_code=409,
            details={
                "action": action,
                "phase": phase,
                "allowedActions": list(allowed_actions or []),
            },
        )


class WorkflowContextStaleError(WorkflowV2Error):
    def __init__(self, project_id: str, node_id: str, reason: str | None = None) -> None:
        super().__init__(
            "ERR_WORKFLOW_CONTEXT_STALE",
            "Workflow context is stale. Rebase before continuing.",
            status_code=409,
            details={
                "projectId": project_id,
                "nodeId": node_id,
                "reason": reason,
                "allowedActions": ["rebase_context"],
            },
        )


class WorkflowContextNotStaleError(WorkflowV2Error):
    def __init__(self, project_id: str, node_id: str) -> None:
        super().__init__(
            "ERR_WORKFLOW_CONTEXT_NOT_STALE",
            "Workflow context is not stale.",
            status_code=409,
            details={"projectId": project_id, "nodeId": node_id},
        )


class WorkflowVersionConflictError(WorkflowV2Error):
    def __init__(self, *, expected_version: int, actual_version: int) -> None:
        super().__init__(
            "ERR_WORKFLOW_VERSION_CONFLICT",
            "Workflow state version does not match the expected version.",
            status_code=409,
            details={
                "expectedWorkflowVersion": expected_version,
                "actualWorkflowVersion": actual_version,
            },
        )


class WorkflowThreadBindingFailedError(WorkflowV2Error):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            "ERR_WORKFLOW_THREAD_BINDING_FAILED",
            message,
            status_code=500,
            details=details,
        )


class WorkflowIdempotencyConflictError(WorkflowV2Error):
    def __init__(self, key: str) -> None:
        super().__init__(
            "ERR_WORKFLOW_IDEMPOTENCY_CONFLICT",
            f"Idempotency key {key!r} was already used with a different payload.",
            status_code=409,
            details={"idempotencyKey": key},
        )


class WorkflowArtifactVersionConflictError(WorkflowV2Error):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            "ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT",
            message,
            status_code=409,
            details=details,
        )


class WorkflowExecutionFailedError(WorkflowV2Error):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            "ERR_WORKFLOW_EXECUTION_FAILED",
            message,
            status_code=500,
            details=details,
        )


class WorkflowAuditFailedError(WorkflowV2Error):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            "ERR_WORKFLOW_AUDIT_FAILED",
            message,
            status_code=500,
            details=details,
        )


class WorkflowV2NotImplementedError(WorkflowV2Error):
    def __init__(self, feature: str) -> None:
        super().__init__(
            "ERR_WORKFLOW_NOT_IMPLEMENTED",
            f"Workflow V2 feature {feature!r} is not implemented in this phase.",
            status_code=501,
            details={"feature": feature},
        )
