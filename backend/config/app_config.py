from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AppPaths:
    data_root: Path
    projects_root: Path
    config_root: Path


def get_app_data_root(override: Optional[Path] = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()

    env_override = os.environ.get("PLANNINGTREE_DATA_ROOT")
    if env_override:
        return Path(env_override).expanduser().resolve()

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return (base / "PlanningTree").resolve()


def build_app_paths(data_root: Optional[Path] = None) -> AppPaths:
    root = get_app_data_root(data_root)
    return AppPaths(
        data_root=root,
        projects_root=root / "projects",
        config_root=root / "config",
    )


def get_port() -> int:
    return int(os.environ.get("PLANNINGTREE_PORT", "8000"))


def get_split_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_SPLIT_TIMEOUT_SEC", "120")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 120
    return max(10, min(600, timeout))


def get_frame_gen_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_FRAME_GEN_TIMEOUT_SEC", "120")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 120
    return max(10, min(600, timeout))


def get_clarify_gen_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_CLARIFY_GEN_TIMEOUT_SEC", "120")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 120
    return max(10, min(600, timeout))


def get_spec_gen_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_SPEC_GEN_TIMEOUT_SEC", "120")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 120
    return max(10, min(600, timeout))


def get_chat_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_CHAT_TIMEOUT_SEC", "120")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 120
    return max(10, min(600, timeout))


def get_execution_timeout() -> int:
    raw = os.environ.get("PLANNINGTREE_EXECUTION_TIMEOUT_SEC", "1200")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 1200
    return max(10, min(3600, timeout))


def is_execution_audit_v2_enabled() -> bool:
    raw = str(os.environ.get("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    # Production V2 is now the default path. Rehearsal still needs a way to
    # opt into its isolated branch without also forcing production mode on.
    if is_execution_audit_v2_rehearsal_enabled():
        return False
    return True


def is_execution_audit_v2_rehearsal_enabled() -> bool:
    raw = str(os.environ.get("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_execution_audit_uiux_v3_backend_enabled() -> bool:
    raw = str(os.environ.get("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_execution_audit_uiux_v3_frontend_enabled() -> bool:
    raw = str(os.environ.get("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _read_optional_bool_env(name: str) -> bool | None:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def is_execution_uiux_v3_frontend_enabled() -> bool:
    lane_value = _read_optional_bool_env("PLANNINGTREE_EXECUTION_UIUX_V3_FRONTEND")
    if lane_value is not None:
        return lane_value
    return is_execution_audit_uiux_v3_frontend_enabled()


def is_audit_uiux_v3_frontend_enabled() -> bool:
    lane_value = _read_optional_bool_env("PLANNINGTREE_AUDIT_UIUX_V3_FRONTEND")
    if lane_value is not None:
        return lane_value
    return is_execution_audit_uiux_v3_frontend_enabled()


def get_rehearsal_workspace_root() -> Optional[Path]:
    raw = str(os.environ.get("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", "") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def get_max_chat_message_chars() -> int:
    raw = os.environ.get("PLANNINGTREE_MAX_CHAT_MESSAGE_CHARS", "10000")
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = 10000
    return max(1, limit)


def get_split_model() -> str:
    return os.environ.get("PLANNINGTREE_SPLIT_MODEL", "gpt-4o")


def get_codex_cmd() -> Optional[str]:
    explicit = os.environ.get("PLANNINGTREE_CODEX_CMD")
    if explicit:
        resolved = _resolve_binary(explicit)
        if resolved:
            return resolved

    for candidate in ("codex", "codex.exe", "codex.cmd"):
        resolved = _resolve_binary(candidate)
        if resolved:
            return resolved

    if sys.platform == "win32":
        fallback = _find_windows_vscode_codex()
        if fallback:
            return str(fallback)

    return explicit


def _resolve_binary(command: str) -> str | None:
    candidate = command.strip()
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if path.is_file():
        return str(path.resolve())
    resolved = shutil.which(candidate)
    if resolved:
        return str(Path(resolved).resolve())
    return None


def _find_windows_vscode_codex() -> Path | None:
    extension_roots = [
        Path.home() / ".vscode" / "extensions",
        Path.home() / ".vscode-insiders" / "extensions",
    ]
    candidates: list[Path] = []
    for root in extension_roots:
        if not root.exists():
            continue
        for extension_dir in root.glob("openai.chatgpt-*"):
            binary = extension_dir / "bin" / "windows-x86_64" / "codex.exe"
            if binary.is_file():
                candidates.append(binary)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]
