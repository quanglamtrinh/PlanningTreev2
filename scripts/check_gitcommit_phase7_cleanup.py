from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SPLIT_SERVICE_PATH = ROOT / "backend" / "services" / "split_service.py"
NODE_DETAIL_SERVICE_PATH = ROOT / "backend" / "services" / "node_detail_service.py"
WORKFLOW_SERVICE_PATH = ROOT / "backend" / "business" / "workflow_v2" / "execution_audit_orchestrator.py"
WORKFLOW_INTEGRATION_TEST_PATH = ROOT / "backend" / "tests" / "integration" / "test_workflow_v4_phase5.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    text = _read(path)
    module = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            if node.end_lineno is None:
                break
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    raise RuntimeError(f"Function {function_name!r} not found in {path.as_posix()}")


def _check_split_does_not_write_execution_state(failures: list[str]) -> None:
    text = _read(SPLIT_SERVICE_PATH)
    if "workflow_domain_store.write_execution" in text:
        failures.append(
            "split_service must not write execution projections; split commit metadata must remain workflow-owned.",
        )


def _check_node_detail_read_order_contract(failures: list[str]) -> None:
    text = _read(NODE_DETAIL_SERVICE_PATH)
    required_tokens = [
        'def _resolve_commit_projection(',
        'initial_sha = _normalize_optional_string(exec_state.get("initial_sha"))',
        'head_sha = _normalize_optional_string(exec_state.get("head_sha"))',
        'commit_message = _normalize_optional_string(exec_state.get("commit_message"))',
    ]
    for token in required_tokens:
        if token not in text:
            failures.append(
                f"node_detail_service is missing required V2 commit projection token: {token}",
            )


def _check_audit_accept_does_not_overwrite_head_commit(failures: list[str]) -> None:
    accept_source = _function_source(WORKFLOW_SERVICE_PATH, "accept_audit")
    if "head_commit_sha" in accept_source:
        failures.append("accept_audit must not overwrite head_commit_sha.")

    required_writers = {
        "mark_done_from_execution": "head_commit_sha",
        "start_audit": "head_commit_sha",
    }
    for function_name, token in required_writers.items():
        fn_source = _function_source(WORKFLOW_SERVICE_PATH, function_name)
        if token not in fn_source:
            failures.append(f"{function_name} must write {token}.")


def _check_idempotency_regression_tests_present(failures: list[str]) -> None:
    text = _read(WORKFLOW_INTEGRATION_TEST_PATH)
    required_tests = [
        "test_v4_execution_start_uses_v2_orchestrator_and_is_idempotent",
        "test_v2_orchestrator_direct_settlement_is_idempotent_when_no_active_run",
        "test_audit_settlement_uses_final_review_message_for_improve_prompt",
    ]
    for test_name in required_tests:
        if test_name not in text:
            failures.append(
                f"Required workflow V2 idempotency/regression test is missing: {test_name}",
            )


def main() -> int:
    failures: list[str] = []
    _check_split_does_not_write_execution_state(failures)
    _check_node_detail_read_order_contract(failures)
    _check_audit_accept_does_not_overwrite_head_commit(failures)
    _check_idempotency_regression_tests_present(failures)

    if failures:
        print("Gitcommit Phase 7 cleanup check failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print("Gitcommit Phase 7 cleanup check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
