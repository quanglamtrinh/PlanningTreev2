from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from backend.config.app_config import AppPaths
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    @property
    def auth_path(self) -> Path:
        return self._paths.config_root / "auth.json"

    def read_auth_config(self) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        return load_json(self.auth_path, default={}) or {}

    def write_auth_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ensure_dir(self._paths.config_root)
        atomic_write_json(self.auth_path, payload)
        return payload
