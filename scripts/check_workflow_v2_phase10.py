from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def method_segment(content: str, method_name: str) -> str:
    pattern = re.compile(rf"^    def {re.escape(method_name)}\(", re.MULTILINE)
    match = pattern.search(content)
    if match is None:
        return ""
    next_match = re.search(r"^    def \w+\(", content[match.end() :], re.MULTILINE)
    if next_match is None:
        return content[match.start() :]
    return content[match.start() : match.end() + next_match.start()]


def route_handler_segment(content: str, route: str) -> str:
    marker = f'@router.{route}'
    start = content.find(marker)
    if start < 0:
        return ""
    next_route = content.find("@router.", start + len(marker))
    if next_route < 0:
        return content[start:]
    return content[start:next_route]


def check_adapter_and_routes(errors: list[str]) -> None:
    adapter_path = ROOT / "backend/business/workflow_v2/legacy_v3_adapter.py"
    require(errors, adapter_path.exists(), "Missing Phase 10 V3 compatibility adapter.")
    adapter = adapter_path.read_text(encoding="utf-8") if adapter_path.exists() else ""
    require(errors, "class LegacyWorkflowV3CompatibilityAdapter" in adapter, "Adapter class is missing.")
    require(errors, "WORKFLOW_V3_DEPRECATION_HEADERS" in adapter, "V3 deprecation headers are missing.")
    require(errors, "WorkflowV3CompatMode" in adapter, "V3 compat mode support is missing.")

    main = read("backend/main.py")
    require(errors, "LegacyWorkflowV3CompatibilityAdapter" in main, "backend/main.py does not construct the V3 compat adapter.")
    require(errors, "app.state.workflow_v3_compat_adapter" in main, "backend/main.py does not expose workflow_v3_compat_adapter.")

    routes = read("backend/routes/workflow_v3.py")
    require(errors, "def _workflow_v3_adapter(request: Request)" in routes, "workflow_v3 route adapter accessor is missing.")
    require(errors, "WORKFLOW_V3_DEPRECATION_HEADERS" in routes, "workflow_v3 routes do not attach deprecation headers.")
    require(errors, "def _workflow_service(" not in routes, "workflow_v3 routes still define the legacy service accessor.")
    require(
        errors,
        "execution_audit_workflow_service" not in routes,
        "workflow_v3 routes still reference the legacy execution/audit workflow service.",
    )

    workflow_routes = [
        'get("/projects/{project_id}/nodes/{node_id}/workflow-state")',
        'post("/projects/{project_id}/nodes/{node_id}/workflow/finish-task")',
        'post("/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution")',
        'post("/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit")',
        'post("/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit")',
        'post("/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution")',
    ]
    for route in workflow_routes:
        segment = route_handler_segment(routes, route)
        require(errors, bool(segment), f"Missing V3 compatibility route handler: {route}")
        require(errors, "_workflow_v3_adapter(request)" in segment, f"V3 route does not call adapter: {route}")
        require(errors, "_deprecated_ok(" in segment, f"V3 route does not return deprecated success envelope: {route}")
        require(errors, "deprecated=True" in segment, f"V3 route does not mark WorkflowV2Error as deprecated: {route}")
        require(errors, "_workflow_service(request)" not in segment, f"V3 route still calls legacy workflow service: {route}")
        require(
            errors,
            "execution_audit_workflow_service" not in segment,
            f"V3 route still references legacy workflow service state: {route}",
        )


def check_execution_audit_service_is_not_fallback_owner(errors: list[str]) -> None:
    service = read("backend/services/execution_audit_workflow_service.py")
    orchestrator = read("backend/business/workflow_v2/execution_audit_orchestrator.py")
    require(
        errors,
        "backend.services.execution_audit_workflow_service" not in orchestrator,
        "Workflow V2 orchestrator still imports helpers from the legacy workflow service.",
    )
    require(
        errors,
        "backend.business.workflow_v2.execution_audit_helpers" in orchestrator,
        "Workflow V2 orchestrator does not use Workflow V2 execution/audit helpers.",
    )
    require(errors, "def _require_workflow_orchestrator_v2" in service, "ExecutionAuditWorkflowService lacks fail-closed V2 guard.")
    for method in [
        "get_workflow_state",
        "finish_task",
        "mark_done_from_execution",
        "review_in_audit",
        "improve_in_execution",
        "mark_done_from_audit",
    ]:
        segment = method_segment(service, method)
        require(errors, bool(segment), f"Missing ExecutionAuditWorkflowService.{method}.")
        require(
            errors,
            "_require_workflow_orchestrator_v2()" in segment,
            f"ExecutionAuditWorkflowService.{method} does not require Workflow Core V2.",
        )
        forbidden_tokens = [
            "_get_cached_mutation(",
            "_store_cached_mutation(",
            "_start_execution_run(",
            "_run_review_cycle_background",
            "workflow_state_store.write_state",
        ]
        for token in forbidden_tokens:
            require(errors, token not in segment, f"Legacy fallback token remains in {method}: {token}")

    followup_segment = method_segment(service, "start_execution_followup")
    require(errors, bool(followup_segment), "Missing ExecutionAuditWorkflowService.start_execution_followup.")
    require(
        errors,
        "ERR_WORKFLOW_V3_EXECUTION_FOLLOWUP_DEPRECATED" in followup_segment,
        "Legacy execution follow-up still has a mutating implementation.",
    )
    for token in ["_start_execution_run(", "workflow_state_store.write_state", "_store_cached_mutation("]:
        require(errors, token not in followup_segment, f"Legacy execution follow-up still contains token: {token}")


def check_frontend_active_path(errors: list[str]) -> None:
    node_editor = read("frontend/src/features/node/NodeDocumentEditor.tsx")
    require(errors, "useWorkflowStateV2" in node_editor, "NodeDocumentEditor does not use Workflow V2 state.")
    require(errors, "startExecution" in node_editor, "NodeDocumentEditor does not start execution through Workflow V2.")
    for token in ["useWorkflowStateStoreV3", "finishTaskWorkflowV3", "activeMutations[detailStateKey]"]:
        require(errors, token not in node_editor, f"NodeDocumentEditor still contains V3 workflow token: {token}")

    breadcrumb = read("frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx")
    for token in ["useWorkflowStateStoreV3", "useWorkflowEventBridgeV3", "resolveWorkflowProjection"]:
        require(errors, token not in breadcrumb, f"Breadcrumb active path still contains legacy V3 token: {token}")
    for token in ["useWorkflowStateV2", "useWorkflowEventBridgeV2", "buildWorkflowProjectionV2"]:
        require(errors, token in breadcrumb, f"Breadcrumb active path is missing Workflow V2 token: {token}")

    import_pattern = re.compile(r"import\s+.*useWorkflowStateStoreV3|from ['\"].*workflowStateStoreV3['\"]")
    allowed_import_files = {
        "frontend/src/features/conversation/state/workflowStateStoreV3.ts",
    }
    for path in (ROOT / "frontend/src").rglob("*.tsx"):
        relative = path.relative_to(ROOT).as_posix()
        if relative in allowed_import_files:
            continue
        content = path.read_text(encoding="utf-8")
        require(errors, import_pattern.search(content) is None, f"Production TSX imports V3 workflow store: {relative}")


def check_session_v4_is_session_only(errors: list[str]) -> None:
    session_v4 = read("backend/routes/session_v4.py")
    forbidden = [
        "ExecutionAuditWorkflowService",
        "execution_audit_workflow_service",
        "workflow_state_store",
        "mark_done_from_execution",
        "review_in_audit",
        "improve_in_execution",
        "mark_done_from_audit",
    ]
    for token in forbidden:
        require(errors, token not in session_v4, f"/v4/session route contains workflow business token: {token}")


def check_tests_cover_phase10(errors: list[str]) -> None:
    adapter_tests = read("backend/tests/unit/test_workflow_v3_compat_adapter.py")
    for token in [
        "finish_task",
        "mark_done_from_execution",
        "review_in_audit",
        "improve_in_execution",
        "mark_done_from_audit",
        "read_only",
        "off",
        "WORKFLOW_V3_DEPRECATION_HEADERS",
    ]:
        require(errors, token in adapter_tests, f"Phase 10 adapter test coverage is missing token: {token}")

    route_guard = read("backend/tests/unit/test_phase4_workflow_v3_control_plane_guards.py")
    for route in [
        "/workflow-state",
        "/workflow/finish-task",
        "/workflow/mark-done-from-execution",
        "/workflow/review-in-audit",
        "/workflow/mark-done-from-audit",
        "/workflow/improve-in-execution",
    ]:
        require(errors, route in route_guard, f"Route guard is missing V3 compatibility route: {route}")


def main() -> int:
    errors: list[str] = []
    check_adapter_and_routes(errors)
    check_execution_audit_service_is_not_fallback_owner(errors)
    check_frontend_active_path(errors)
    check_session_v4_is_session_only(errors)
    check_tests_cover_phase10(errors)

    if errors:
        print("Workflow V2 Phase 10 guard FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Workflow V2 Phase 10 guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
