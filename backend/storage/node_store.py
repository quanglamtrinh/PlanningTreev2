from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.storage.node_files import (
    create_node_directory,
    default_state,
    empty_brief,
    empty_briefing,
    empty_spec,
    empty_task,
    load_all as load_all_node_files,
    read_brief,
    read_briefing,
    read_plan,
    read_spec,
    read_state,
    read_task,
    write_brief,
    write_briefing,
    write_plan,
    write_spec,
    write_state,
    write_task,
)
from backend.storage.project_ids import normalize_project_id


class NodeStore:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def _project_dir(self, project_id: str) -> Path:
        return self._paths.projects_root / normalize_project_id(project_id)

    def _nodes_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "nodes"

    def node_dir(self, project_id: str, node_id: str) -> Path:
        return self._nodes_dir(project_id) / node_id

    def create_node_files(
        self,
        project_id: str,
        node_id: str,
        task: dict[str, str] | None = None,
        brief: dict[str, Any] | None = None,
        briefing: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
    ) -> Path:
        node_path = self.node_dir(project_id, node_id)
        create_node_directory(
            node_path,
            task=task or empty_task(),
            brief=brief or briefing or empty_brief(),
            spec=spec or empty_spec(),
            state=state or default_state(),
        )
        return node_path

    def load_all(self, project_id: str, node_id: str) -> dict[str, Any]:
        return load_all_node_files(self.node_dir(project_id, node_id))

    def load_task(self, project_id: str, node_id: str) -> dict[str, str]:
        return read_task(self.node_dir(project_id, node_id))

    def load_brief(self, project_id: str, node_id: str) -> dict[str, Any]:
        return read_brief(self.node_dir(project_id, node_id))

    def load_briefing(self, project_id: str, node_id: str) -> dict[str, Any]:
        return read_briefing(self.node_dir(project_id, node_id))

    def load_spec(self, project_id: str, node_id: str) -> dict[str, Any]:
        return read_spec(self.node_dir(project_id, node_id))

    def load_plan(self, project_id: str, node_id: str) -> dict[str, str]:
        return read_plan(self.node_dir(project_id, node_id))

    def load_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        return read_state(self.node_dir(project_id, node_id))

    def save_task(self, project_id: str, node_id: str, task: dict[str, str]) -> None:
        write_task(self.node_dir(project_id, node_id), task)

    def save_brief(self, project_id: str, node_id: str, brief: dict[str, Any]) -> None:
        write_brief(self.node_dir(project_id, node_id), brief)

    def save_briefing(self, project_id: str, node_id: str, briefing: dict[str, Any]) -> None:
        write_briefing(self.node_dir(project_id, node_id), briefing)

    def save_spec(self, project_id: str, node_id: str, spec: dict[str, Any]) -> None:
        write_spec(self.node_dir(project_id, node_id), spec)

    def save_plan(self, project_id: str, node_id: str, plan: dict[str, str]) -> None:
        write_plan(self.node_dir(project_id, node_id), plan)

    def save_state(self, project_id: str, node_id: str, state: dict[str, Any]) -> None:
        write_state(self.node_dir(project_id, node_id), state)

    def delete_node_files(self, project_id: str, node_id: str) -> None:
        node_path = self.node_dir(project_id, node_id)
        if node_path.exists():
            shutil.rmtree(node_path)

    def node_exists(self, project_id: str, node_id: str) -> bool:
        node_path = self.node_dir(project_id, node_id)
        required_files = ("task.md", "briefing.md", "spec.md", "state.yaml")
        return node_path.is_dir() and all((node_path / name).is_file() for name in required_files)
