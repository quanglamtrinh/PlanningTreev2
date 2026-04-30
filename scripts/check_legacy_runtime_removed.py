from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PREFIXES = ("backend/", "frontend/", "scripts/")
SCAN_FILENAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "planningtree-server.spec",
}
IGNORED_SUFFIXES = (
    ".tsbuildinfo",
    ".pyc",
)
IGNORED_PARTS = {
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
}


def _removed_tokens() -> list[str]:
    return [
        "/" + "v3/",
        "ASK_" + "V3",
        "CONVERSATION_" + "V3",
        "THREAD_" + "ACTOR_MODE",
        "ThreadRuntimeService" + "V3",
        "ThreadQueryService" + "V3",
        "CodexApp" + "Client",
        "backend." + "conversation",
        "chat_" + "state_store",
        "execution_" + "state_store",
        "review_" + "state_store",
        "split_" + "state_store",
        "_legacy_" + "message_item",
        "LegacyProject" + "Unsupported",
        "legacy_projects_" + "purged",
        "Codex" + "Snapshot",
        "Codex" + "Account",
        "Codex" + "RateLimits",
        "AskRollout" + "Metrics",
        "threadByIdStore" + "V3",
        "Messages" + "V3",
        "applyThreadEvent" + "V3",
        "session" + "V2Adapters",
        "codex-" + "store",
        "codex/account",
        "codex/events",
        "codex/usage/local",
        "backend.routes." + "split",
        "backend.config." + "api_version",
    ]


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for raw in result.stdout.splitlines():
        rel = raw.strip()
        if not rel:
            continue
        rel_path = Path(rel)
        rel_posix = rel_path.as_posix()
        if not (
            rel_posix.startswith(SCAN_PREFIXES)
            or rel_path.name in SCAN_FILENAMES
            or rel_path.parent.as_posix() == "frontend" and rel_path.name in SCAN_FILENAMES
        ):
            continue
        if rel_posix == "scripts/check_legacy_runtime_removed.py":
            continue
        if rel_path.suffix in IGNORED_SUFFIXES:
            continue
        if any(part in IGNORED_PARTS for part in rel_path.parts):
            continue
        path = ROOT / rel_path
        if path.is_file():
            paths.append(path)
    return paths


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def main() -> int:
    failures: list[str] = []
    tokens = _removed_tokens()
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for token in tokens:
            rel_index = rel.find(token)
            if rel_index != -1:
                failures.append(f"{rel} contains removed legacy path token {token!r}")
            index = text.find(token)
            if index != -1:
                failures.append(f"{rel}:{_line_number(text, index)} contains removed legacy token {token!r}")

    if failures:
        print("Legacy runtime removal guard failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print("Legacy runtime removal guard passed.")
    print(f"scanned_files={len(_tracked_files())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
