import os
import sys
from pathlib import Path


def get_app_data_root() -> Path:
    """Return the platform-appropriate app data directory."""
    override = os.environ.get("PLANNINGTREE_DATA_ROOT")
    if override:
        return Path(override)

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / "PlanningTree"


def get_port() -> int:
    return int(os.environ.get("PLANNINGTREE_PORT", "8000"))


def get_split_timeout() -> int:
    return int(os.environ.get("PLANNINGTREE_SPLIT_TIMEOUT_SEC", "120"))


def get_split_model() -> str:
    return os.environ.get("PLANNINGTREE_SPLIT_MODEL", "gpt-4o")


def get_codex_cmd() -> str | None:
    return os.environ.get("PLANNINGTREE_CODEX_CMD")


APP_DATA_ROOT = get_app_data_root()
PROJECTS_ROOT = APP_DATA_ROOT / "projects"
CONFIG_ROOT = APP_DATA_ROOT / "config"
