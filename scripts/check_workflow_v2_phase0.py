from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "docs" / "migration"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_contains(errors: list[str], text: str, needle: str, label: str) -> None:
    if needle not in text:
        errors.append(f"{label} missing required text: {needle}")


def main() -> int:
    errors: list[str] = []

    required_docs = [
        "README.md",
        "session-workflow-v2-contract.md",
        "workflow-v2-roadmap.md",
        "workflow-core-v2-architecture.md",
        "workflow-v2-api-contract.md",
        "workflow-v2-cutover-checklist.md",
        "phase-0-gate-report-v1.md",
        "phase-6-breadcrumb-v2-cutover-plan-v1.md",
        "phase-7-end-to-end-workflow-actions-plan-v1.md",
    ]
    for rel in required_docs:
        if not (MIGRATION / rel).exists():
            errors.append(f"missing migration doc: {rel}")

    if errors:
        print("WORKFLOW_V2_PHASE0_CHECK=FAIL")
        for error in errors:
            print("-", error)
        return 1

    readme = read(MIGRATION / "README.md")
    roadmap = read(MIGRATION / "workflow-v2-roadmap.md")
    contract = read(MIGRATION / "session-workflow-v2-contract.md")
    api_contract = read(MIGRATION / "workflow-v2-api-contract.md")
    architecture = read(MIGRATION / "workflow-core-v2-architecture.md")
    checklist = read(MIGRATION / "workflow-v2-cutover-checklist.md")
    report = read(MIGRATION / "phase-0-gate-report-v1.md")

    docs_by_label = [
        ("README", readme),
        ("roadmap", roadmap),
        ("contract", contract),
        ("api contract", api_contract),
        ("architecture", architecture),
        ("checklist", checklist),
        ("gate report", report),
    ]

    for label, text in docs_by_label:
        require_contains(errors, text, "/v4/session/*", label)

    for label, text in [
        ("roadmap", roadmap),
        ("contract", contract),
        ("api contract", api_contract),
        ("gate report", report),
    ]:
        require_contains(errors, text, "/v4/projects/{projectId}/nodes/{nodeId}", label)

    phase_pairs = {
        "`idle`": "`ready_for_execution`",
        "`execution_running`": "`executing`",
        "`execution_decision_pending`": "`execution_completed`",
        "`audit_running`": "`audit_running`",
        "`audit_decision_pending`": "`review_pending`",
        "`done`": "`done`",
        "`failed`": "`blocked`",
    }
    for label, text in [
        ("roadmap", roadmap),
        ("contract", contract),
        ("api contract", api_contract),
        ("architecture", architecture),
        ("gate report", report),
    ]:
        for legacy, canonical in phase_pairs.items():
            require_contains(errors, text, legacy, label)
            require_contains(errors, text, canonical, label)

    for label, text in [
        ("roadmap", roadmap),
        ("contract", contract),
        ("api contract", api_contract),
        ("gate report", report),
    ]:
        require_contains(errors, text, "execution/improve", label)
        require_contains(errors, text, "audit/request-changes", label)

    require_contains(errors, api_contract, '"schemaVersion": 1', "api contract")
    require_contains(errors, api_contract, '"version": 42', "api contract")
    require_contains(errors, contract, "Canonical V2 wire naming", "contract")
    require_contains(errors, architecture, "state_version", "architecture")
    require_contains(errors, readme, "Phase 0 Gate Report", "README")
    require_contains(errors, checklist, "Phase 0 contract gate", "checklist")

    for label, text in [
        ("README", readme),
        ("roadmap", roadmap),
        ("architecture", architecture),
        ("checklist", checklist),
        ("gate report", report),
    ]:
        require_contains(errors, text, "thread/inject_items", label)

    session_v4 = read(ROOT / "backend" / "routes" / "session_v4.py")
    main_py = read(ROOT / "backend" / "main.py")
    breadcrumb_controller = read(
        ROOT
        / "frontend"
        / "src"
        / "features"
        / "conversation"
        / "useBreadcrumbConversationControllerV2.tsx"
    )
    workflow_state_store = read(ROOT / "backend" / "storage" / "workflow_state_store.py")

    require_contains(errors, main_py, "app.include_router(workflow_v3.router, prefix=API_PREFIX)", "backend main")
    require_contains(errors, main_py, "app.include_router(session_v4.router)", "backend main")
    require_contains(errors, session_v4, '"/v4/session/threads/{threadId}/inject-items"', "session_v4")
    require_contains(errors, session_v4, "thread/inject_items", "session_v4")
    require_contains(errors, breadcrumb_controller, "useSessionFacadeV2", "Breadcrumb controller")
    require_contains(errors, breadcrumb_controller, "useWorkflowStateV2", "Breadcrumb controller")
    require_contains(errors, breadcrumb_controller, "useWorkflowEventBridgeV2", "Breadcrumb controller")
    require_contains(errors, workflow_state_store, '"workflow_v2"', "WorkflowStateStore")
    require_contains(errors, workflow_state_store, '"workflowPhase"', "WorkflowStateStore")

    forbidden_breadcrumb_terms = [
        "useWorkflowStateStoreV3",
        "useWorkflowEventBridgeV3",
        "reviewInAudit",
        "markDoneFromExecution",
        "improveInExecution",
        "markDoneFromAudit",
    ]
    for forbidden in forbidden_breadcrumb_terms:
        if forbidden in breadcrumb_controller:
            errors.append(f"Breadcrumb controller should stay on Workflow V2, found: {forbidden}")

    forbidden_session_route_terms = [
        "execution_audit_workflow_service",
        "workflow_state_store",
        "workflow_v3",
        "reviewInAudit",
        "markDoneFromExecution",
    ]
    for forbidden in forbidden_session_route_terms:
        if forbidden in session_v4:
            errors.append(f"session_v4 should stay session-only, found: {forbidden}")

    if errors:
        print("WORKFLOW_V2_PHASE0_CHECK=FAIL")
        for error in errors:
            print("-", error)
        return 1

    print("WORKFLOW_V2_PHASE0_CHECK=PASS")
    print(f"checked_docs={len(required_docs)}")
    print("route_family=/v4/projects/{projectId}/nodes/{nodeId}/...")
    print("session_boundary=/v4/session/*")
    print("current_boundary=session-v2-workflow-v2-breadcrumb-with-legacy-adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
