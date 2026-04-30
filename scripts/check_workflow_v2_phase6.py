from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    controller_path = "frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx"
    controller = _read(controller_path)
    if not controller:
        errors.append(f"Missing Breadcrumb controller: {controller_path}")
    else:
        for token in (
            "useSessionFacadeV2",
            "useWorkflowStateV2",
            "useWorkflowEventBridgeV2",
            "buildWorkflowProjectionV2",
            "startExecution",
            "completeExecution",
            "startAudit",
            "improveExecution",
            "acceptAudit",
        ):
            if token not in controller:
                errors.append(f"{controller_path} is missing Phase 6 token: {token}")
        for forbidden in (
            "useWorkflowStateStoreV3",
            "useWorkflowEventBridgeV3",
            "resolveWorkflowProjection",
            "reviewInAudit",
            "markDoneFromExecution",
            "improveInExecution",
            "markDoneFromAudit",
        ):
            if forbidden in controller:
                errors.append(f"{controller_path} still contains V3 workflow token: {forbidden}")

    required_frontend = {
        "frontend/src/features/workflow_v2/api/client.ts": [
            "startExecutionV2",
            "markDoneFromExecutionV2",
            "startAuditV2",
            "improveExecutionV2",
            "acceptAuditV2",
            "/v4/projects/",
        ],
        "frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts": [
            "activeMutations",
            "startExecution",
            "completeExecution",
            "startAudit",
            "improveExecution",
            "acceptAudit",
            "newIdempotencyKey",
        ],
        "frontend/src/features/workflow_v2/hooks/useWorkflowEventBridgeV2.ts": [
            "workflow/action_completed",
            "workflow/action_failed",
        ],
        "frontend/src/features/conversation/workflowThreadLaneV2.ts": [
            "WorkflowStateV2",
            "buildWorkflowProjectionV2",
            "start_execution",
            "review_in_audit",
            "mark_done_from_execution",
            "improve_in_execution",
            "mark_done_from_audit",
        ],
    }
    for relative_path, tokens in required_frontend.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 6 file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 6 token: {token}")

    scoped_sources = {
        "frontend/src/features/workflow_v2/api/client.ts": _read(
            "frontend/src/features/workflow_v2/api/client.ts"
        ),
        "frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx": controller,
    }
    for relative_path, source in scoped_sources.items():
        removed_projects_prefix = "/v" + "3/projects/"
        if removed_projects_prefix in source and "/workflow" in source:
            errors.append(f"{relative_path} must not call V3 workflow endpoints in Phase 6.")

    session_v4 = _read("backend/routes/session_v4.py")
    for token in (
        "workflow_thread_binding_service_v2",
        "WorkflowEventPublisherV2",
        "WorkflowStateRepositoryV2",
        "/v4/projects/{projectId}/nodes/{nodeId}",
    ):
        if token in session_v4:
            errors.append(f"session_v4 must remain workflow-business-free, found: {token}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Workflow V2 Phase 6 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
