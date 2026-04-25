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
        errors.append(f"{label} is missing Phase 8 token: {token}")


def main() -> int:
    errors: list[str] = []

    routes = _read("backend/routes/workflow_v4.py")
    thread_binding = _read("backend/business/workflow_v2/thread_binding.py")
    models = _read("backend/business/workflow_v2/models.py")
    state_machine = _read("backend/business/workflow_v2/state_machine.py")
    client = _read("frontend/src/features/workflow_v2/api/client.ts")
    store = _read("frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts")
    hook = _read("frontend/src/features/workflow_v2/hooks/useWorkflowStateV2.ts")
    projection = _read("frontend/src/features/conversation/workflowThreadLaneV2.ts")
    controller = _read("frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx")
    session_v4 = _read("backend/routes/session_v4.py")
    backend_phase8_tests = _read("backend/tests/integration/test_workflow_v4_phase8.py") + "\n" + _read(
        "backend/tests/unit/test_workflow_v2_context_rebase.py"
    )
    frontend_tests = _read("frontend/tests/unit/workflowStateStoreV2.test.ts") + "\n" + _read(
        "frontend/tests/unit/workflowThreadLaneV2.test.ts"
    ) + "\n" + _read("frontend/tests/unit/BreadcrumbChatViewV2.workflow-v2.integration.test.tsx")

    for token in (
        '"/v4/projects/{projectId}/nodes/{nodeId}/context/rebase"',
        "rebase_workflow_context_v4",
        "ContextRebaseRequest",
    ):
        _require(errors, routes, token, "Workflow V4 routes")

    for token in (
        "def rebase_context",
        "refresh_context_freshness",
        "context_update",
        "thread_inject_items",
        "WorkflowVersionConflictError",
        "WorkflowContextNotStaleError",
    ):
        _require(errors, thread_binding, token, "Workflow V2 thread binding/rebase service")

    for token in (
        "ContextStaleBindingV2",
        "staleBindings",
        "context_stale_details",
    ):
        _require(errors, models, token, "Workflow V2 models")

    for token in (
        "def rebase_context",
        '"rebase_context"',
    ):
        _require(errors, state_machine, token, "Workflow V2 state machine")

    for token in (
        "rebaseContextV2",
        "/context/rebase",
    ):
        _require(errors, client, token, "Workflow V2 API client")

    for token in (
        "rebaseContext",
        "rebaseContextV2",
        "context_rebase",
        "rebase_context",
    ):
        _require(errors, store, token, "Workflow V2 store")
        _require(errors, hook, "rebaseContext", "Workflow V2 hook")

    for token in (
        "workflow-rebase-context",
        "Rebase Context",
        "'rebase_context'",
    ):
        _require(errors, projection, token, "Workflow V2 lane projection")

    for token in (
        "rebaseContext",
        "expectedWorkflowVersion",
    ):
        _require(errors, controller, token, "Breadcrumb controller")

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
        "context/rebase",
    ):
        if forbidden in session_v4:
            errors.append(f"session_v4 must remain workflow-business-free, found: {forbidden}")

    for token in (
        "staleBindings",
        "context/rebase",
        "context_update",
        "ERR_WORKFLOW_VERSION_CONFLICT",
    ):
        _require(errors, backend_phase8_tests, token, "Phase 8 backend tests")

    for token in (
        "workflow-rebase-context",
        "rebaseContext",
        "context_rebase",
    ):
        _require(errors, frontend_tests, token, "Phase 8 frontend tests")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Workflow V2 Phase 8 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
