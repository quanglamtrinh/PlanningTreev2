from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_IMPLEMENTATION = {
    "backend/business/workflow_v2/models.py": [
        "thread_bindings",
        "class ThreadBinding",
    ],
    "backend/business/workflow_v2/context_packets.py": [
        "def canonical_json",
        "sort_keys=True",
        "def packet_hash",
        "def render_model_visible_message",
    ],
    "backend/business/workflow_v2/context_builder.py": [
        "class WorkflowContextBuilderV2",
        '"ask_planning_context"',
        '"child_activation_context"',
        '"execution_context"',
        '"audit_context"',
        '"package_review_context"',
        '"context_update"',
        '"splitManifestVersion": None',
    ],
    "backend/business/workflow_v2/thread_binding.py": [
        "class ThreadBindingServiceV2",
        "def ensure_thread",
        "thread_start",
        "thread_inject_items",
        '"legacy_adopted"',
        '"new_thread"',
        "WorkflowContextStaleError",
        "WorkflowIdempotencyConflictError",
    ],
    "backend/routes/workflow_v4.py": [
        '"/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/ensure"',
        "class EnsureThreadRequest",
        "workflow_thread_binding_service_v2",
    ],
    "backend/main.py": [
        "WorkflowStateRepositoryV2",
        "WorkflowContextBuilderV2",
        "ThreadBindingServiceV2",
        "app.include_router(workflow_v4.router)",
    ],
}

REQUIRED_TESTS = {
    "backend/tests/unit/test_workflow_v2_context_packets.py": [
        "test_context_packet_hash_is_stable_for_dict_key_order",
        "test_rendered_context_message_contains_canonical_json",
        "test_builder_produces_expected_role_kinds_and_source_versions",
    ],
    "backend/tests/unit/test_workflow_v2_thread_binding.py": [
        "test_new_thread_starts_injects_context_and_persists_binding",
        "test_matching_existing_binding_reuses_thread_without_inject",
        "test_legacy_thread_id_is_adopted_and_receives_initial_context",
        "test_changed_context_without_force_rebase_marks_stale_and_raises",
        "test_changed_context_with_force_rebase_injects_context_update",
        "test_idempotency_replay_and_conflict",
    ],
    "backend/tests/integration/test_workflow_v4_ensure_thread.py": [
        "test_v4_ensure_thread_returns_direct_contract_shape",
        "test_v4_ensure_thread_rejects_invalid_role",
        "test_v4_ensure_thread_returns_session_not_initialized_error",
        "test_session_v4_routes_remain_workflow_business_free",
    ],
}


def _read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    for relative_path, tokens in REQUIRED_IMPLEMENTATION.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 3 file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 3 token: {token}")

    workflow_v4 = _read("backend/routes/workflow_v4.py")
    post_route_count = len(re.findall(r"@router\.post\(", workflow_v4))
    if post_route_count != 1:
        errors.append(
            "workflow_v4.py must expose exactly one Phase 3 workflow mutation route; "
            f"found {post_route_count} POST routes."
        )

    session_v4 = _read("backend/routes/session_v4.py")
    for token in (
        "workflow_thread_binding_service_v2",
        "ThreadBindingServiceV2",
        "ExecutionAuditWorkflowService",
        "/v4/projects/{projectId}/nodes/{nodeId}",
    ):
        if token in session_v4:
            errors.append(f"session_v4 must remain workflow-business-free, found: {token}")

    for relative_path, tokens in REQUIRED_TESTS.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 3 test file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 3 test token: {token}")

    for script in (
        "scripts/check_workflow_v2_phase0.py",
        "scripts/check_workflow_v2_phase1.py",
        "scripts/check_workflow_v2_phase2.py",
    ):
        result = subprocess.run([sys.executable, script], cwd=str(ROOT), check=False)
        if result.returncode != 0:
            errors.append(f"{script} failed.")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Workflow V2 Phase 3 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
