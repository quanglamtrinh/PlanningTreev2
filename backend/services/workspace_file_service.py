from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.errors.app_errors import InvalidRequest, NodeNotFound, WorkspaceFileNotFound
from backend.services import planningtree_workspace
from backend.storage.file_utils import atomic_write_text, load_text
from backend.storage.storage import Storage


class WorkspaceFileService:
    """Read/write UTF-8 text files under project, root-node, or node-local scopes."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def _project_path(self, project_id: str) -> Path:
        return Path(self._storage.workspace_store.get_folder_path(project_id))

    def _normalize_relative_path(self, relative_path: str) -> str:
        raw = str(relative_path or "").strip().replace("\\", "/")
        if not raw or len(raw) > 2048:
            raise InvalidRequest("relative_path is required and must be under 2048 characters.")
        candidate_rel = Path(raw)
        if candidate_rel.is_absolute() or ".." in candidate_rel.parts:
            raise InvalidRequest("relative_path must be relative and cannot contain '..'.")
        return raw

    def _resolve_under_base(self, base_path: Path, relative_path: str) -> tuple[Path, str]:
        raw = self._normalize_relative_path(relative_path)
        base_resolved = base_path.resolve()
        target = (base_path / Path(raw)).resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError as exc:
            raise InvalidRequest("relative_path escapes the selected directory.") from exc
        return target, raw

    def _resolve_target(
        self,
        project_id: str,
        relative_path: str,
        *,
        scope: str = "workspace",
        node_id: str | None = None,
    ) -> tuple[Path, str]:
        project_path = self._project_path(project_id)
        normalized_scope = str(scope or "workspace").strip()
        if normalized_scope == "workspace":
            return self._resolve_under_base(project_path, relative_path)

        snapshot = self._storage.project_store.load_snapshot(project_id)
        if normalized_scope == "root_node":
            target_node_id = str(snapshot.get("tree_state", {}).get("root_node_id") or "").strip()
        elif normalized_scope == "node":
            target_node_id = str(node_id or "").strip()
        else:
            raise InvalidRequest("scope must be 'workspace', 'root_node', or 'node'.")
        if not target_node_id:
            raise InvalidRequest("node_id is required for node-scoped workspace files.")

        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, target_node_id)
        if node_dir is None:
            raise NodeNotFound(target_node_id)
        return self._resolve_under_base(node_dir, relative_path)

    def get_text_file(
        self,
        project_id: str,
        relative_path: str,
        *,
        scope: str = "workspace",
        node_id: str | None = None,
    ) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            path, normalized_relative_path = self._resolve_target(
                project_id, relative_path, scope=scope, node_id=node_id
            )
            if not path.is_file():
                raise WorkspaceFileNotFound(f"Not a file or missing: {normalized_relative_path}")
            return {
                "relative_path": normalized_relative_path,
                "content": load_text(path),
                "updated_at": _path_updated_at(path),
            }

    def put_text_file(
        self,
        project_id: str,
        relative_path: str,
        content: str,
        *,
        scope: str = "workspace",
        node_id: str | None = None,
    ) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            path, normalized_relative_path = self._resolve_target(
                project_id, relative_path, scope=scope, node_id=node_id
            )
            atomic_write_text(path, content)
            return {
                "relative_path": normalized_relative_path,
                "content": content,
                "updated_at": _path_updated_at(path),
            }

def _path_updated_at(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
