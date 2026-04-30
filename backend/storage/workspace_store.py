from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_ids import normalize_project_id


class WorkspaceStore:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    @property
    def path(self) -> Path:
        return self._paths.config_root / "workspace.json"

    def read(self) -> dict[str, Any]:
        ensure_dir(self._paths.config_root)
        raw = load_json(self.path, default={}) or {}
        entries: list[dict[str, str]] = []
        raw_entries = raw.get("entries")
        if isinstance(raw_entries, list):
            seen_project_ids: set[str] = set()
            seen_paths: set[str] = set()
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                project_id = item.get("project_id")
                folder_path = item.get("folder_path")
                if not isinstance(project_id, str) or not isinstance(folder_path, str):
                    continue
                try:
                    normalized_id = normalize_project_id(project_id)
                except Exception:
                    continue
                normalized_path = self._normalize_folder_path(folder_path)
                if normalized_id in seen_project_ids or normalized_path in seen_paths:
                    continue
                entries.append(
                    {
                        "project_id": normalized_id,
                        "folder_path": normalized_path,
                    }
                )
                seen_project_ids.add(normalized_id)
                seen_paths.add(normalized_path)
        return {
            "entries": entries,
        }

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        entries: list[dict[str, str]] = []
        for item in payload.get("entries", []):
            if not isinstance(item, dict):
                continue
            project_id = item.get("project_id")
            folder_path = item.get("folder_path")
            if not isinstance(project_id, str) or not isinstance(folder_path, str):
                continue
            entries.append(
                {
                    "project_id": normalize_project_id(project_id),
                    "folder_path": self._normalize_folder_path(folder_path),
                }
            )
        data = {"entries": entries}
        atomic_write_json(self.path, data)
        return data

    def list_entries(self) -> list[dict[str, str]]:
        return list(self.read()["entries"])

    def get_folder_path(self, project_id: str) -> str:
        normalized_id = normalize_project_id(project_id)
        for item in self.read()["entries"]:
            if item["project_id"] == normalized_id:
                return item["folder_path"]
        raise ProjectNotFound(project_id)

    def find_project_id_by_folder(self, folder_path: str) -> str | None:
        normalized_path = self._normalize_folder_path(folder_path)
        for item in self.read()["entries"]:
            if item["folder_path"] == normalized_path:
                return item["project_id"]
        return None

    def upsert_entry(self, project_id: str, folder_path: str) -> dict[str, str]:
        normalized_id = normalize_project_id(project_id)
        normalized_path = self._normalize_folder_path(folder_path)
        state = self.read()
        entries = [
            item
            for item in state["entries"]
            if item["project_id"] != normalized_id and item["folder_path"] != normalized_path
        ]
        entry = {
            "project_id": normalized_id,
            "folder_path": normalized_path,
        }
        entries.append(entry)
        state["entries"] = entries
        self.write(state)
        return entry

    def remove_project(self, project_id: str) -> None:
        normalized_id = normalize_project_id(project_id)
        state = self.read()
        state["entries"] = [
            item for item in state["entries"] if item["project_id"] != normalized_id
        ]
        self.write(state)

    def prune_projects(self, project_ids: list[str]) -> None:
        normalized_ids = {normalize_project_id(project_id) for project_id in project_ids}
        state = self.read()
        state["entries"] = [
            item for item in state["entries"] if item["project_id"] not in normalized_ids
        ]
        self.write(state)

    def _normalize_folder_path(self, folder_path: str) -> str:
        return str(Path(folder_path).expanduser().resolve())
