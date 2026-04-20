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


def is_ask_v3_backend_enabled() -> bool:
    return _bool_env("PLANNINGTREE_ASK_V3_BACKEND_ENABLED", default=True)


def is_ask_v3_frontend_enabled() -> bool:
    return _bool_env("PLANNINGTREE_ASK_V3_FRONTEND_ENABLED", default=True)


def is_ask_followup_queue_enabled() -> bool:
    return _bool_env("PLANNINGTREE_ASK_FOLLOWUP_QUEUE_ENABLED", default=False)


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


def get_conversation_v3_bridge_mode() -> str:
    raw = str(os.environ.get("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "") or "").strip().lower()
    if raw in {"enabled", "allowlist", "disabled"}:
        return raw
    return "enabled"


def get_conversation_v3_bridge_allowlist() -> set[str]:
    raw = str(os.environ.get("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", "") or "").strip()
    if not raw:
        return set()
    return {entry.strip() for entry in raw.split(",") if entry.strip()}


def get_thread_actor_mode() -> str:
    raw = str(os.environ.get("PLANNINGTREE_THREAD_ACTOR_MODE", "") or "").strip().lower()
    if raw in {"off", "shadow", "on"}:
        return raw
    return "off"


def get_sse_subscriber_queue_max() -> int:
    raw = os.environ.get("PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX", "128")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 128
    return max(1, min(4096, value))


def is_session_core_v2_turns_enabled() -> bool:
    return _bool_env("SESSION_CORE_V2_ENABLE_TURNS", default=True)


def is_session_core_v2_events_enabled() -> bool:
    return _bool_env("SESSION_CORE_V2_ENABLE_EVENTS", default=True)


def get_session_core_v2_event_queue_capacity() -> int:
    raw = os.environ.get("SESSION_CORE_V2_EVENT_QUEUE_CAPACITY", "128")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 128
    return max(1, min(4096, value))


def get_session_core_v2_retention_max_events() -> int:
    raw = os.environ.get("SESSION_CORE_V2_RETENTION_MAX_EVENTS", "200000")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 200000
    return max(1, value)


def get_session_core_v2_retention_days() -> int:
    raw = os.environ.get("SESSION_CORE_V2_RETENTION_DAYS", "7")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 7
    return max(1, value)


def get_phase5_log_compact_min_events() -> int:
    raw = os.environ.get("PLANNINGTREE_P05_LOG_COMPACT_MIN_EVENTS", "200")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 200
    return max(1, value)


def get_thread_stream_cadence_profile() -> str:
    raw = str(os.environ.get("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "") or "").strip().lower()
    if raw in {"low", "standard", "high"}:
        return raw
    return "high"


def get_thread_raw_event_coalesce_ms() -> int:
    raw = str(os.environ.get("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS", "") or "").strip()
    if raw:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 50
        return max(10, min(80, value))

    profile = get_thread_stream_cadence_profile()
    profile_defaults = {
        "low": 60,
        "standard": 25,
        "high": 20,
    }
    return profile_defaults.get(profile, 25)


def is_conversation_v3_bridge_allowed_for_project(project_id: str) -> bool:
    mode = get_conversation_v3_bridge_mode()
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    return str(project_id or "").strip() in get_conversation_v3_bridge_allowlist()


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


def _bool_env(name: str, *, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)
