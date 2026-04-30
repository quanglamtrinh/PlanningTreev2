from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSION_V4_ROUTE = ROOT / "backend" / "routes" / "session_v4.py"
FRONTEND_APP = ROOT / "frontend" / "src" / "App.tsx"
SESSION_V2_ROOT = ROOT / "frontend" / "src" / "features" / "session_v2"


def main() -> int:
    errors: list[str] = []

    if not SESSION_V4_ROUTE.exists():
        errors.append(f"missing route file: {SESSION_V4_ROUTE}")
    else:
        route_text = SESSION_V4_ROUTE.read_text(encoding="utf-8")
        required_enabled_markers = [
            'def session_thread_fork_v4(',
            'def session_thread_turns_v4(',
            'def session_thread_loaded_list_v4(',
            'def session_thread_unsubscribe_v4(',
            'thread_fork(',
            'thread_turns_list(',
            'thread_loaded_list(',
            'thread_unsubscribe(',
        ]
        for marker in required_enabled_markers:
            if marker not in route_text:
                errors.append(f"phase4 route marker missing: {marker}")
        forbidden_phase_markers = [
            '_phase_not_enabled("thread/fork"',
            '_phase_not_enabled("thread/turns/list"',
            '_phase_not_enabled("thread/loaded/list"',
            '_phase_not_enabled("thread/unsubscribe"',
        ]
        for marker in forbidden_phase_markers:
            if marker in route_text:
                errors.append(f"phase4 route still gated: {marker}")

    if not FRONTEND_APP.exists():
        errors.append(f"missing frontend app file: {FRONTEND_APP}")
    else:
        app_text = FRONTEND_APP.read_text(encoding="utf-8")
        if '/session-v2' not in app_text:
            errors.append("frontend route '/session-v2' is missing in App.tsx")
        if "SessionConsoleV2" not in app_text:
            errors.append("SessionConsoleV2 is not wired in App.tsx")

    if not SESSION_V2_ROOT.exists():
        errors.append(f"missing frontend session_v2 root: {SESSION_V2_ROOT}")
    else:
        required_files = [
            SESSION_V2_ROOT / "shell" / "SessionConsoleV2.tsx",
            SESSION_V2_ROOT / "store" / "threadSessionStore.ts",
            SESSION_V2_ROOT / "store" / "connectionStore.ts",
            SESSION_V2_ROOT / "store" / "pendingRequestsStore.ts",
            SESSION_V2_ROOT / "state" / "applySessionEvent.ts",
            SESSION_V2_ROOT / "state" / "sessionEventParser.ts",
            SESSION_V2_ROOT / "api" / "client.ts",
        ]
        for path in required_files:
            if not path.exists():
                errors.append(f"missing phase4 frontend file: {path.relative_to(ROOT)}")

        forbidden_import_fragments = [
            "threadByIdStore" + "V3",
            "workflowStateStoreV3",
            "workflowEventBridgeV3",
            "BreadcrumbChatViewV2",
            "features/conversation",
        ]
        for file_path in SESSION_V2_ROOT.rglob("*.ts*"):
            text = file_path.read_text(encoding="utf-8")
            for fragment in forbidden_import_fragments:
                if fragment in text:
                    errors.append(
                        f"forbidden legacy reference in {file_path.relative_to(ROOT)}: {fragment}"
                    )

    if errors:
        print("PHASE4_CONTRACT_CHECK=FAIL")
        for error in errors:
            print("-", error)
        return 1

    print("PHASE4_CONTRACT_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
