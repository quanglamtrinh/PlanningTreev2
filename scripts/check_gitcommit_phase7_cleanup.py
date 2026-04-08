from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SPLIT_SERVICE_PATH = ROOT / "backend" / "services" / "split_service.py"
NODE_DETAIL_SERVICE_PATH = ROOT / "backend" / "services" / "node_detail_service.py"
WORKFLOW_SERVICE_PATH = ROOT / "backend" / "services" / "execution_audit_workflow_service.py"
WORKFLOW_INTEGRATION_TEST_PATH = ROOT / "backend" / "tests" / "integration" / "test_workflow_v2_review_thread_context.py"


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
    if "execution_state_store" in text:
        failures.append(
            "split_service must not touch execution_state_store; split commit metadata must remain workflow-owned.",
        )


def _check_node_detail_read_order_contract(failures: list[str]) -> None:
    text = _read(NODE_DETAIL_SERVICE_PATH)
    required_tokens = [
        'latest_commit = workflow_state.get("latestCommit") or workflow_state.get("latest_commit")',
        'initial_sha = _latest_commit_value(latest_commit, "initialSha", "initial_sha")',
        'head_sha = _latest_commit_value(latest_commit, "headSha", "head_sha")',
        'commit_message = _latest_commit_value(latest_commit, "commitMessage", "commit_message")',
        'if initial_sha is None:',
        'if head_sha is None:',
        'if commit_message is None:',
    ]
    for token in required_tokens:
        if token not in text:
            failures.append(
                f"node_detail_service is missing required fallback token: {token}",
            )


def _check_mark_done_from_audit_does_not_write_latest_commit(failures: list[str]) -> None:
    mark_done_source = _function_source(WORKFLOW_SERVICE_PATH, "mark_done_from_audit")
    if "latestCommit" in mark_done_source:
        failures.append("mark_done_from_audit must not write latestCommit.")

    for required_fn in ("mark_done_from_execution", "review_in_audit"):
        fn_source = _function_source(WORKFLOW_SERVICE_PATH, required_fn)
        if "latestCommit" not in fn_source:
            failures.append(f"{required_fn} must write latestCommit.")


def _check_idempotency_regression_tests_present(failures: list[str]) -> None:
    text = _read(WORKFLOW_INTEGRATION_TEST_PATH)
    required_tests = [
        "test_first_review_cycle_uses_detached_thread_with_project_workspace",
        "test_mark_done_from_execution_persists_latest_commit_and_idempotency",
        "test_mark_done_from_audit_reuses_existing_latest_commit_without_overwrite",
    ]
    for test_name in required_tests:
        if test_name not in text:
            failures.append(
                f"Required gitcommit idempotency/regression test is missing: {test_name}",
            )


def main() -> int:
    failures: list[str] = []
    _check_split_does_not_write_execution_state(failures)
    _check_node_detail_read_order_contract(failures)
    _check_mark_done_from_audit_does_not_write_latest_commit(failures)
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
