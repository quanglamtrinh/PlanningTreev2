from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "backend/business/__init__.py",
    "backend/business/workflow_v2/__init__.py",
    "backend/business/workflow_v2/models.py",
    "backend/business/workflow_v2/state_machine.py",
    "backend/business/workflow_v2/repository.py",
    "backend/business/workflow_v2/thread_binding.py",
    "backend/business/workflow_v2/context_packets.py",
    "backend/business/workflow_v2/context_builder.py",
    "backend/business/workflow_v2/artifact_orchestrator.py",
    "backend/business/workflow_v2/execution_audit_orchestrator.py",
    "backend/business/workflow_v2/events.py",
    "backend/business/workflow_v2/errors.py",
]

FORBIDDEN_STATE_MACHINE_IMPORTS = [
    "backend.storage",
    "backend.routes",
    "session_core",
    "sse",
    "codex",
    "ExecutionAuditWorkflowService",
            "execution_audit_" + "workflow_service",
]


def main() -> int:
    errors: list[str] = []
    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).exists():
            errors.append(f"Missing required Phase 1 file: {relative_path}")

    state_machine_path = ROOT / "backend/business/workflow_v2/state_machine.py"
    source = state_machine_path.read_text(encoding="utf-8") if state_machine_path.exists() else ""
    for token in FORBIDDEN_STATE_MACHINE_IMPORTS:
        if token in source:
            errors.append(f"Forbidden state_machine import/reference: {token}")

    repository_path = ROOT / "backend/business/workflow_v2/repository.py"
    repository_source = repository_path.read_text(encoding="utf-8") if repository_path.exists() else ""
    if "workflow_core_v2" not in repository_source:
        errors.append("Repository does not reference canonical workflow_core_v2 storage path.")
    if "LEGACY_PHASE_TO_V2" in repository_source:
        errors.append("Repository must not retain legacy phase conversion after runtime removal.")

    phase0 = subprocess.run(
        [sys.executable, "scripts/check_workflow_v2_phase0.py"],
        cwd=str(ROOT),
        check=False,
    )
    if phase0.returncode != 0:
        errors.append("Phase 0 checker failed.")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Workflow V2 Phase 1 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

