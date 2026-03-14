from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from backend.config.app_config import AppPaths
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    @property
    def app_path(self) -> Path:
        return self._paths.config_root / "app.json"

    @property
    def auth_path(self) -> Path:
        return self._paths.config_root / "auth.json"

    def read_app_config(self) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        raw = load_json(self.app_path, default={}) or {}
        return {
            "base_workspace_root": raw.get("base_workspace_root"),
        }

    def write_app_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        data = {
            "base_workspace_root": payload.get("base_workspace_root"),
        }
        atomic_write_json(self.app_path, data)
        return data

    def get_base_workspace_root(self) -> Optional[str]:
        value = self.read_app_config().get("base_workspace_root")
        return value if isinstance(value, str) and value.strip() else None

    def set_base_workspace_root(self, base_workspace_root: Optional[str]) -> Dict[str, Any]:
        return self.write_app_config({"base_workspace_root": base_workspace_root})

    def read_auth_config(self) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        return load_json(self.auth_path, default={}) or {}

    def write_auth_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        atomic_write_json(self.auth_path, payload)
        return payload
