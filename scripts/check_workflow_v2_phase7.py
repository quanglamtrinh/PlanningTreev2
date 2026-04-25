from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _require(errors: list[str], source: str, token: str, label: str) -> None:
    if token not in source:
        errors.append(f"{label} is missing Phase 7 token: {token}")


def main() -> int:
    errors: list[str] = []

    controller = _read("frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx")
    projection = _read("frontend/src/features/conversation/workflowThreadLaneV2.ts")
    client = _read("frontend/src/features/workflow_v2/api/client.ts")
    store = _read("frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts")
    hook = _read("frontend/src/features/workflow_v2/hooks/useWorkflowStateV2.ts")
    routes = _read("backend/routes/workflow_v4.py")
    orchestrator = _read("backend/business/workflow_v2/execution_audit_orchestrator.py")
    state_machine = _read("backend/business/workflow_v2/state_machine.py")
    session_v4 = _read("backend/routes/session_v4.py")

    for token in (
        "ensureThread",
        "'ask_planning'",
        "autoEnsureRole",
        "startPackageReview",
        "'start_package_review'",
        "buildChatV2Url(projectId, nodeId, 'package')",
    ):
        _require(errors, controller, token, "Breadcrumb controller")

    for token in (
        "start_package_review",
        "workflow-start-package-review",
        "threads.packageReview",
    ):
        _require(errors, projection, token, "Workflow V2 lane projection")

    for token in (
        "startPackageReviewV2",
        "/package-review/start",
    ):
        _require(errors, client, token, "Workflow V2 API client")

    for token in (
        "startPackageReview",
        "startPackageReviewV2",
        "start_package_review",
    ):
        _require(errors, store, token, "Workflow V2 store")
        _require(errors, hook, "startPackageReview", "Workflow V2 hook")

    for token in (
        '"/v4/projects/{projectId}/nodes/{nodeId}/package-review/start"',
        "start_package_review_v4",
    ):
        _require(errors, routes, token, "Workflow V4 routes")

    for token in (
        "def start_package_review",
        "role=\"package_review\"",
        "build_package_review_prompt",
        "handle_session_event",
        "turn/completed",
        "publish_action_completed",
    ):
        _require(errors, orchestrator, token, "Workflow V2 orchestrator")

    for token in (
        "def start_package_review",
        "\"start_package_review\"",
        "package_review_thread_id",
    ):
        _require(errors, state_machine, token, "Workflow V2 state machine")

    for forbidden in (
        "useWorkflowStateStoreV3",
        "useWorkflowEventBridgeV3",
        "reviewInAudit",
        "markDoneFromExecution",
        "improveInExecution",
        "markDoneFromAudit",
    ):
        if forbidden in controller:
            errors.append(f"Breadcrumb controller must stay Workflow V2-only, found: {forbidden}")

    scoped_frontend = client + "\n" + store + "\n" + controller + "\n" + projection
    if "/v3/projects/" in scoped_frontend and "/workflow" in scoped_frontend:
        errors.append("Workflow V2 frontend active path must not call V3 workflow endpoints.")

    for forbidden in (
        "execution_audit_workflow_service",
        "workflow_thread_binding_service_v2",
        "ExecutionAuditOrchestratorV2",
        "/v4/projects/{projectId}/nodes/{nodeId}",
        "package-review/start",
    ):
        if forbidden in session_v4:
            errors.append(f"session_v4 must remain workflow-business-free, found: {forbidden}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Workflow V2 Phase 7 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
