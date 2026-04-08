from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.errors.app_errors import InvalidRequest, WorkspaceFileNotFound
from backend.storage.file_utils import atomic_write_text, load_text
from backend.storage.storage import Storage


class WorkspaceFileService:
    """Read/write UTF-8 text files under the attached project folder (no traversal)."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def _project_path(self, project_id: str) -> Path:
        return Path(self._storage.workspace_store.get_folder_path(project_id))

    def _resolve_safe(self, project_path: Path, relative_path: str) -> Path:
        raw = str(relative_path or "").strip().replace("\\", "/")
        if not raw or len(raw) > 2048:
            raise InvalidRequest("relative_path is required and must be under 2048 characters.")
        candidate_rel = Path(raw)
        if candidate_rel.is_absolute() or ".." in candidate_rel.parts:
            raise InvalidRequest("relative_path must be relative and cannot contain '..'.")

        project_resolved = project_path.resolve()
        target = (project_path / candidate_rel).resolve()
        try:
            target.relative_to(project_resolved)
        except ValueError as exc:
            raise InvalidRequest("relative_path escapes the project directory.") from exc
        return target

    def get_text_file(self, project_id: str, relative_path: str) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            project_path = self._project_path(project_id)
            path = self._resolve_safe(project_path, relative_path)
            if not path.is_file():
                raise WorkspaceFileNotFound(f"Not a file or missing: {relative_path}")
            return {
                "relative_path": relative_path.strip().replace("\\", "/"),
                "content": load_text(path),
                "updated_at": _path_updated_at(path),
            }

    def put_text_file(self, project_id: str, relative_path: str, content: str) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            project_path = self._project_path(project_id)
            path = self._resolve_safe(project_path, relative_path)
            atomic_write_text(path, content)
            return {
                "relative_path": relative_path.strip().replace("\\", "/"),
                "content": content,
                "updated_at": _path_updated_at(path),
            }


def _path_updated_at(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
