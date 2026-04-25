from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_IMPLEMENTATION = {
    "backend/session_core_v2/protocol/client.py": [
        "def thread_inject_items",
        '"thread/inject_items"',
    ],
    "backend/session_core_v2/threads/service.py": [
        "def thread_inject_items",
        "session_core_v2 thread/inject_items",
    ],
    "backend/session_core_v2/connection/manager.py": [
        "def thread_inject_items",
        'action_type="thread/inject_items"',
        "record_idempotent_result",
    ],
    "backend/routes/session_v4.py": ["class InjectItemsRequest", "def session_inject_items_v4"],
}

REQUIRED_TEST_TOKENS = {
    "backend/tests/unit/test_session_v2_protocol_client.py": [
        "test_protocol_client_maps_thread_inject_items",
    ],
    "backend/tests/integration/test_session_v4_api.py": [
        "test_session_v4_inject_items_idempotent_without_starting_turn",
        "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH",
    ],
}

FORBIDDEN_MANAGER_TOKENS = [
    "turn_start(",
    ".turn_start(",
    "create_turn(",
    "transition_turn(",
]


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
            errors.append(f"Missing required Phase 2 file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 2 token: {token}")

    route_source = _read("backend/routes/session_v4.py")
    if "def session_inject_items_not_enabled" in route_source:
        errors.append("Inject-items route is still the Phase 2 stub.")

    manager_source = _read("backend/session_core_v2/connection/manager.py")
    match = re.search(r"def thread_inject_items\(.*?\n    def model_list\(", manager_source, re.S)
    manager_method = match.group(0) if match else ""
    if not manager_method:
        errors.append("Could not locate SessionManagerV2.thread_inject_items body.")
    else:
        for token in FORBIDDEN_MANAGER_TOKENS:
            if token in manager_method:
                errors.append(f"thread_inject_items must not start or transition turns: {token}")

    for relative_path, tokens in REQUIRED_TEST_TOKENS.items():
        source = _read(relative_path)
        if not source:
            errors.append(f"Missing required Phase 2 test file: {relative_path}")
            continue
        for token in tokens:
            if token not in source:
                errors.append(f"{relative_path} is missing Phase 2 test token: {token}")

    for script in ("scripts/check_workflow_v2_phase0.py", "scripts/check_workflow_v2_phase1.py"):
        result = subprocess.run([sys.executable, script], cwd=str(ROOT), check=False)
        if result.returncode != 0:
            errors.append(f"{script} failed.")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Workflow V2 Phase 2 gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
