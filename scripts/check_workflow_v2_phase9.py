from __future__ import annotations

import re
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
        errors.append(f"{label} is missing Phase 9 token: {token}")


def main() -> int:
    errors: list[str] = []

    orchestrator = _read("backend/business/workflow_v2/artifact_orchestrator.py")
    routes = _read("backend/routes/artifacts_v4.py")
    main_py = _read("backend/main.py")
    events = _read("backend/business/workflow_v2/events.py")
    workflow_routes = _read("backend/routes/workflow_v4.py")
    session_v4 = _read("backend/routes/session_v4.py")
    frontend_api = _read("frontend/src/api/client.ts")
    event_bridge = _read("frontend/src/features/workflow_v2/hooks/useWorkflowEventBridgeV2.ts")
    backend_tests = _read("backend/tests/unit/test_workflow_v2_artifact_orchestrator.py") + "\n" + _read(
        "backend/tests/integration/test_workflow_v4_phase9.py"
    )
    frontend_tests = _read("frontend/tests/unit/workflowEventBridgeV2.test.tsx")
    phase9_doc = _read("docs/migration/phase-9-artifact-orchestrator-alignment-plan-v1.md")

    for token in (
        "class ArtifactOrchestratorV2",
        "sync_artifact_source_versions",
        "start_frame_generation",
        "confirm_frame",
        "start_split",
        "workflow/artifact_confirmed",
    ):
        _require(errors, orchestrator, token, "ArtifactOrchestratorV2")

    if "WorkflowV2NotImplementedError" in orchestrator:
        errors.append("ArtifactOrchestratorV2 must no longer be a Phase 1 stub.")

    for token in (
        "/v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/generate",
        "/v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/confirm",
        "/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/confirm",
        "/v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/confirm",
        "/v4/projects/{projectId}/nodes/{nodeId}/artifacts/split/start",
        "/v4/projects/{projectId}/artifact-jobs/split/status",
    ):
        _require(errors, routes, token, "V4 artifact routes")

    for token in (
        "ArtifactOrchestratorV2",
        "artifact_orchestrator_v2",
        "artifacts_v4.router",
    ):
        _require(errors, main_py, token, "backend main wiring")

    for token in (
        "workflow/artifact_job_started",
        "workflow/artifact_job_completed",
        "workflow/artifact_job_failed",
        "workflow/artifact_confirmed",
        "workflow/artifact_state_changed",
        "publish_artifact_event",
    ):
        _require(errors, events + "\n" + workflow_routes, token, "Workflow V2 artifact events")

    for token in (
        "/v4/projects/",
        "/frame/generate",
        "/frame/confirm",
        "/clarify/generate",
        "/clarify/confirm",
        "/spec/generate",
        "/spec/confirm",
        "/split/start",
        "/artifact-jobs/split/status",
        "idempotencyKey",
    ):
        _require(errors, frontend_api, token, "frontend V4 artifact API path")

    forbidden_frontend_patterns = (
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/generate-frame",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/confirm-frame",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/generate-clarify",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/confirm-clarify",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/generate-spec",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/confirm-spec",
        r"/v3/projects/[^`'\"]+/nodes/[^`'\"]+/split",
        r"/v3/projects/[^`'\"]+/split-status",
    )
    for pattern in forbidden_frontend_patterns:
        if re.search(pattern, frontend_api):
            errors.append(f"frontend active artifact API must use V4, found pattern: {pattern}")

    for forbidden in (
        "artifact_orchestrator",
        "frame_generation_service",
        "clarify_generation_service",
        "spec_generation_service",
        "split_service",
        "workflowArtifact",
        "artifact_summary",
    ):
        if forbidden in session_v4:
            errors.append(f"session_v4 must remain artifact-workflow-free, found: {forbidden}")

    for token in (
        "workflow/artifact_confirmed",
        "workflow/artifact_state_changed",
    ):
        _require(errors, event_bridge, token, "Workflow V2 event bridge")

    for token in (
        "syncs_source_versions",
        "workflow/artifact_confirmed",
        "artifacts/frame/confirm",
    ):
        _require(errors, backend_tests, token, "Phase 9 backend tests")

    _require(errors, frontend_tests, "workflow/artifact_confirmed", "Phase 9 frontend tests")

    for token in (
        "Status: complete.",
        "ArtifactOrchestratorV2",
        "scripts/check_workflow_v2_phase9.py",
    ):
        _require(errors, phase9_doc, token, "Phase 9 migration doc")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Workflow V2 Phase 9 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
