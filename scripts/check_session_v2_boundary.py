from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSION_V2_ROOT = ROOT / "frontend" / "src" / "features" / "session_v2"

CODE_EXTENSIONS = {".ts", ".tsx", ".css"}

IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?[\"']([^\"']+)[\"']"
    r"|import\s*\(\s*[\"']([^\"']+)[\"']\s*\)",
    re.MULTILINE,
)

FORBIDDEN_IMPORT_FRAGMENTS = {
    "features/conversation": "conversation feature imports stay outside session_v2",
    "features/graph": "graph feature imports stay outside session_v2",
    "features/project": "project feature imports stay outside session_v2",
    "features/node": "node feature imports stay outside session_v2",
    "workflowStateStore": "workflow store imports stay outside session_v2",
    "workflowEventBridge": "workflow event bridge imports stay outside session_v2",
    "threadByIdStoreV3": "legacy conversation stores stay outside session_v2",
    "codex-store": "legacy global codex store imports stay outside session_v2",
    "project-store": "project store imports stay outside session_v2",
    "detail-state-store": "project/detail workflow store imports stay outside session_v2",
    "node-document-store": "project artifact store imports stay outside session_v2",
    "ask-shell-action-store": "lane shell action store imports stay outside session_v2",
}

FORBIDDEN_RESOLVED_PREFIXES = [
    (ROOT / "frontend" / "src" / "features" / "conversation", "conversation feature imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "features" / "graph", "graph feature imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "features" / "project", "project feature imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "features" / "node", "node feature imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "stores" / "project-store", "project store imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "stores" / "detail-state-store", "project/detail workflow store imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "stores" / "node-document-store", "project artifact store imports stay outside session_v2"),
    (ROOT / "frontend" / "src" / "stores" / "ask-shell-action-store", "lane shell action store imports stay outside session_v2"),
]

LANE_TOKEN_PATTERNS = [
    (re.compile(r"(?<![A-Za-z0-9_])(ask|execution|audit)(?![A-Za-z0-9_])"), "lane literal"),
    (re.compile(r"(?<![A-Za-z0-9_])(Ask|Execution|Audit)(?![A-Za-z0-9_])"), "lane literal"),
    (re.compile(r"(?<![A-Za-z0-9_])(ask|execution|audit)(?=[A-Z0-9_])"), "lane-prefixed identifier"),
    (re.compile(r"(?<=_)(ask|execution|audit)(?![a-z])"), "lane snake-case identifier fragment"),
    (re.compile(r"(?<=[A-Za-z0-9_])(Ask|Execution|Audit)(?![a-z])"), "lane identifier fragment"),
]

ALLOWED_TOKEN_CONTEXTS = {
    "commandExecution",
    "item/commandExecution/requestApproval",
    "item/commandExecution/outputDelta",
    "/commandExecution/",
}


def _iter_code_files() -> list[Path]:
    if not SESSION_V2_ROOT.exists():
        return []
    return sorted(
        path
        for path in SESSION_V2_ROOT.rglob("*")
        if path.is_file() and path.suffix in CODE_EXTENSIONS
    )


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _normalize(value: str) -> str:
    return value.replace("\\", "/")


def _resolve_relative_import(file_path: Path, specifier: str) -> Path | None:
    if not specifier.startswith("."):
        return None
    return (file_path.parent / specifier).resolve()


def _is_path_under(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix.resolve())
        return True
    except ValueError:
        return False


def _check_imports(file_path: Path, text: str, errors: list[str]) -> None:
    for match in IMPORT_RE.finditer(text):
        specifier = match.group(1) or match.group(2) or ""
        normalized_specifier = _normalize(specifier)
        line = _line_number(text, match.start())

        for fragment, reason in FORBIDDEN_IMPORT_FRAGMENTS.items():
            if fragment in normalized_specifier:
                rel_path = file_path.relative_to(ROOT)
                errors.append(
                    f"{rel_path}:{line}: forbidden import '{specifier}' ({reason})"
                )

        resolved = _resolve_relative_import(file_path, specifier)
        if resolved is None:
            continue
        for prefix, reason in FORBIDDEN_RESOLVED_PREFIXES:
            if _is_path_under(resolved, prefix):
                rel_path = file_path.relative_to(ROOT)
                errors.append(
                    f"{rel_path}:{line}: forbidden import '{specifier}' ({reason})"
                )


def _check_lane_tokens(file_path: Path, text: str, errors: list[str]) -> None:
    for pattern, reason in LANE_TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            if _is_allowed_token_context(text, match.start(), match.end()):
                continue
            rel_path = file_path.relative_to(ROOT)
            line = _line_number(text, match.start())
            token = match.group(0)
            errors.append(
                f"{rel_path}:{line}: forbidden session_v2 lane token '{token}' ({reason})"
            )


def _is_allowed_token_context(text: str, start: int, end: int) -> bool:
    left = start
    while left > 0 and re.match(r"[A-Za-z0-9_/-]", text[left - 1]):
        left -= 1

    right = end
    while right < len(text) and re.match(r"[A-Za-z0-9_/-]", text[right]):
        right += 1

    context = text[left:right]
    return context in ALLOWED_TOKEN_CONTEXTS


def main() -> int:
    errors: list[str] = []

    if not SESSION_V2_ROOT.exists():
        errors.append(f"missing frontend session_v2 root: {SESSION_V2_ROOT.relative_to(ROOT)}")
    else:
        for file_path in _iter_code_files():
            text = file_path.read_text(encoding="utf-8")
            _check_imports(file_path, text, errors)
            _check_lane_tokens(file_path, text, errors)

    if errors:
        print("SESSION_V2_BOUNDARY_CHECK=FAIL")
        for error in errors:
            print("-", error)
        return 1

    print("SESSION_V2_BOUNDARY_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
