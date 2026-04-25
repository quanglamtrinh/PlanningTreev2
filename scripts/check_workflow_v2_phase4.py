from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_IMPLEMENTATION = {
    "backend/routes/workflow_v4.py": [
        '"/v4/projects/{projectId}/nodes/{nodeId}/workflow-state"',
        '"/v4/projects/{projectId}/events"',
        "workflow_state_to_response",
        "derive_allowed_actions",
        "workflow/state_changed",
        "node.workflow.updated",
    ],
    "backend/business/workflow_v2/events.py": [
        "class WorkflowEventPublisherV2",
        "publish_state_changed",
        "WorkflowEventV2",
    ],
    "backend/business/workflow_v2/thread_binding.py": [
        "event_publisher",
        "publish_state_changed",
    ],
    "backend/main.py": [
        "WorkflowEventPublisherV2",
        "workflow_event_publisher_v2",
        "event_publisher=workflow_event_publisher_v2",
    ],
    "frontend/src/features/workflow_v2/types.ts": [
        "WorkflowStateV2",
        "WorkflowEventV2",
        "WorkflowActionV2",
    ],
    "frontend/src/features/workflow_v2/api/client.ts": [
        "getWorkflowStateV2",
        "buildProjectEventsUrlV2",
        "openWorkflowEventsStreamV2",
        "/v4/projects/",
    ],
    "frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts": [
        "useWorkflowStateStoreV2",
        "workflowStateInFlight",
        "loadWorkflowState",
    ],
    "frontend/src/features/workflow_v2/hooks/useWorkflowStateV2.ts": [
        "useWorkflowStateV2",
        "useWorkflowStateStoreV2",
    ],
    "frontend/src/features/workflow_v2/hooks/useWorkflowEventBridgeV2.ts": [
        "useWorkflowEventBridgeV2",
        "openWorkflowEventsStreamV2",
        "workflow/state_changed",
    ],
}

REQUIRED_TESTS = {
    "backend/tests/integration/test_workflow_v4_phase4.py": [
        "test_v4_workflow_state_returns_direct_canonical_default",
        "test_v4_workflow_state_read_through_converts_legacy_v3_phase",
        "test_v4_workflow_events_filter_and_adapt_legacy_updates",
        "test_ensure_thread_publishes_state_changed_and_replay_does_not_republish",
        "test_ensure_thread_when_context_changes_publishes_state_changed_only",
    ],
    "frontend/tests/unit/workflowStateStoreV2.test.ts": [
        "dedupes concurrent workflow-state loads",
        "records load errors",
        "resets entries",
    ],
    "frontend/tests/unit/workflowEventBridgeV2.test.tsx": [
        "refreshes workflow state",
        "filters other targets",
        "reconnects after stream errors",
    ],
}


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    for script in (
        "scripts/check_workflow_v2_phase0.py",
        "scripts/check_workflow_v2_phase1.py",
        "scripts/check_workflow_v2_phase2.py",
        "scripts/check_workflow_v2_phase3.py",
    ):
        result = subprocess.run([sys.executable, script], cwd=str(ROOT), check=False)
        if result.returncode != 0:
            errors.append(f"{script} failed.")

    for relative_path, tokens in REQUIRED_IMPLEMENTATION.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 4 file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 4 token: {token}")

    for relative_path, tokens in REQUIRED_TESTS.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 4 test file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 4 test token: {token}")

    breadcrumb_controller = _read("frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx")
    if "features/workflow_v2" in breadcrumb_controller or "useWorkflowStateStoreV2" in breadcrumb_controller:
        errors.append("Breadcrumb V2 controller must not import Workflow V2 before Phase 6.")
    if "useWorkflowStateStoreV3" not in breadcrumb_controller or "useWorkflowEventBridgeV3" not in breadcrumb_controller:
        errors.append("Breadcrumb V2 controller must remain on the V3 workflow bridge during Phase 4.")

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
    print("Workflow V2 Phase 4 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
