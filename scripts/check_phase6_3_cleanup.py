from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

REMOVED_PATHS = [
    Path("backend/routes/chat.py"),
    Path("frontend/src/config/featureFlags.ts"),
    Path("frontend/src/stores/chat-store.ts"),
    Path("frontend/src/features/breadcrumb/LegacyExecutionChatPanel.tsx"),
    Path("frontend/src/features/breadcrumb/LegacyAskPanel.tsx"),
    Path("frontend/src/features/breadcrumb/LegacyPlanningPanel.tsx"),
    Path("frontend/src/features/conversation/adapters/legacyConversationAdapter.ts"),
]

SCAN_DIRS = [
    ROOT / "frontend" / "src",
    ROOT / "frontend" / "tests" / "unit",
    ROOT / "backend",
]

FORBIDDEN_TOKENS = [
    "useChatStore",
    "chat-store",
    "LegacyExecutionChatPanel",
    "LegacyAskPanel",
    "LegacyPlanningPanel",
    "legacyConversationAdapter",
    "useChatSessionStream",
    "useAskSessionStream",
    "getChatSession",
    "sendChatMessage",
    "resetChatSession",
    "chatEventsUrl",
    "getAskSession",
    "resetAskSession",
    "askEventsUrl",
    "VITE_EXECUTION_CONVERSATION_V2_ENABLED",
    "VITE_ASK_CONVERSATION_V2_ENABLED",
    "VITE_PLANNING_CONVERSATION_V2_ENABLED",
]

PRESERVED_ASSERTIONS = [
    (Path("frontend/src/features/breadcrumb/AskConversationPanel.tsx"), "DeltaContextCard"),
    (Path("frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx"), "useAskSidecarStream"),
    (Path("frontend/src/features/graph/GraphWorkspace.tsx"), "usePlanningEventStream"),
    (Path("frontend/src/stores/project-store.ts"), "planningHistoryByNode"),
]


def iter_repo_files(base_dir: Path):
    for path in base_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".svg", ".ico"}:
            continue
        if any(part in {"__pycache__", "node_modules", "dist", ".pytest_cache"} for part in path.parts):
            continue
        yield path


def main() -> int:
    failures: list[str] = []

    for rel_path in REMOVED_PATHS:
        if (ROOT / rel_path).exists():
            failures.append(f"Removed path still exists: {rel_path.as_posix()}")

    for directory in SCAN_DIRS:
        for path in iter_repo_files(directory):
            text = path.read_text(encoding="utf-8")
            rel_path = path.relative_to(ROOT).as_posix()
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    failures.append(f"Forbidden token '{token}' found in {rel_path}")

    for rel_path, required_token in PRESERVED_ASSERTIONS:
        path = ROOT / rel_path
        if not path.exists():
            failures.append(f"Preserved boundary missing: {rel_path.as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        if required_token not in text:
            failures.append(
                f"Preserved boundary assertion failed: {rel_path.as_posix()} missing '{required_token}'"
            )

    if failures:
        print("Phase 6.3 cleanup check failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print("Phase 6.3 cleanup check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
