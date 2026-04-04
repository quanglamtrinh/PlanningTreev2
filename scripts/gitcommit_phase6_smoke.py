from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


TEST_GROUPS: list[tuple[str, list[str]]] = [
    (
        "split latestCommit invariants (diff + no-diff)",
        [
            "backend/tests/unit/test_split_service.py::test_split_service_commits_projection_and_updates_k0_git_head",
            "backend/tests/unit/test_split_service.py::test_split_service_records_latest_commit_on_no_diff_without_overwriting_k0_head",
        ],
    ),
    (
        "execution/audit latestCommit invariants",
        [
            "backend/tests/unit/test_execution_audit_workflow_service.py::test_mark_done_from_execution_writes_latest_commit_metadata",
            "backend/tests/unit/test_execution_audit_workflow_service.py::test_review_in_audit_writes_latest_commit_metadata_and_uses_head_sha",
            "backend/tests/unit/test_execution_audit_workflow_service.py::test_mark_done_from_audit_keeps_existing_latest_commit_metadata",
        ],
    ),
    (
        "workflow integration invariants (retry + detail-state projection)",
        [
            "backend/tests/integration/test_workflow_v2_review_thread_context.py::test_first_review_cycle_uses_detached_thread_with_project_workspace",
            "backend/tests/integration/test_workflow_v2_review_thread_context.py::test_mark_done_from_execution_persists_latest_commit_and_idempotency",
            "backend/tests/integration/test_workflow_v2_review_thread_context.py::test_mark_done_from_audit_reuses_existing_latest_commit_without_overwrite",
        ],
    ),
    (
        "describe fallback invariant",
        [
            "backend/tests/unit/test_node_detail_service_audit_v2.py::test_detail_state_falls_back_to_execution_state_when_latest_commit_missing",
        ],
    ),
]


def _run_pytest_cases(cases: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", *cases]
    print(f"[gitcommit-smoke] running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=ROOT)
    return completed.returncode


def _run_once(iteration: int, total: int) -> int:
    print(f"[gitcommit-smoke] iteration {iteration}/{total}")
    for label, cases in TEST_GROUPS:
        print(f"[gitcommit-smoke] group: {label}")
        code = _run_pytest_cases(cases)
        if code != 0:
            print(f"[gitcommit-smoke] FAILED group: {label}")
            return code
    print(f"[gitcommit-smoke] iteration {iteration}/{total} PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 6 observe-only smoke for gitcommit rework invariants. "
            "Use --repeat 2 for the internal-stage gate."
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of full sequential smoke passes to run (default: 1).",
    )
    args = parser.parse_args()

    repeat = max(1, int(args.repeat))
    for i in range(1, repeat + 1):
        code = _run_once(i, repeat)
        if code != 0:
            return code
    print("[gitcommit-smoke] all iterations PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
