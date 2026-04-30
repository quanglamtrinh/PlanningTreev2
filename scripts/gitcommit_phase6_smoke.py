from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


TEST_GROUPS: list[tuple[str, list[str]]] = [
    (
        "workflow state-machine commit invariants",
        [
            "backend/tests/unit/test_workflow_v2_state_machine.py::test_mark_done_from_execution_validates_workspace_hash",
            "backend/tests/unit/test_workflow_v2_state_machine.py::test_mark_done_from_audit_validates_review_commit",
        ],
    ),
    (
        "workflow v4 execution/audit invariants",
        [
            "backend/tests/integration/test_workflow_v4_phase5.py::test_v4_execution_start_uses_v2_orchestrator_and_is_idempotent",
            "backend/tests/integration/test_workflow_v4_phase5.py::test_v2_orchestrator_direct_settlement_is_idempotent_when_no_active_run",
            "backend/tests/integration/test_workflow_v4_phase5.py::test_audit_settlement_uses_final_review_message_for_improve_prompt",
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
