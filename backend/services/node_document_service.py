from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.errors.app_errors import InvalidRequest, NodeNotFound
from backend.services import planningtree_workspace
from backend.storage.file_utils import atomic_write_text, load_text
from backend.storage.storage import Storage

DocumentKind = str
_DOCUMENT_KINDS: tuple[DocumentKind, ...] = ("frame", "spec")
_DOCUMENT_FILENAMES: dict[DocumentKind, str] = {
    "frame": planningtree_workspace.FRAME_FILE_NAME,
    "spec": planningtree_workspace.SPEC_FILE_NAME,
}


class NodeDocumentService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def get_document(self, project_id: str, node_id: str, kind: str) -> dict[str, str | None]:
        document_kind = self._normalize_kind(kind)
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            project_path = self._project_path_from_snapshot(snapshot)
            node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
            if node_dir is None:
                raise NodeNotFound(node_id)
            document_path = node_dir / _DOCUMENT_FILENAMES[document_kind]
            return {
                "node_id": node_id,
                "kind": document_kind,
                "content": load_text(document_path),
                "updated_at": _path_updated_at(document_path),
            }

    def put_document(
        self,
        project_id: str,
        node_id: str,
        kind: str,
        content: str,
    ) -> dict[str, str | None]:
        document_kind = self._normalize_kind(kind)
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            self._require_node(snapshot, node_id)
            project_path = self._project_path_from_snapshot(snapshot)
            node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
            if node_dir is None:
                raise NodeNotFound(node_id)
            document_path = node_dir / _DOCUMENT_FILENAMES[document_kind]
            atomic_write_text(document_path, content)
            return {
                "node_id": node_id,
                "kind": document_kind,
                "content": content,
                "updated_at": _path_updated_at(document_path),
            }

    def _normalize_kind(self, kind: str) -> DocumentKind:
        normalized = str(kind or "").strip().lower()
        if normalized not in _DOCUMENT_KINDS:
            raise InvalidRequest("Document kind must be either 'frame' or 'spec'.")
        return normalized

    def _require_node(self, snapshot: dict, node_id: str) -> None:
        tree_state = snapshot.get("tree_state", {})
        node_index = tree_state.get("node_index", {}) if isinstance(tree_state, dict) else {}
        if not isinstance(node_index, dict) or node_id not in node_index:
            raise NodeNotFound(node_id)

    def _project_path_from_snapshot(self, snapshot: dict) -> Path:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            raise InvalidRequest("Project snapshot is missing project metadata.")
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise InvalidRequest("Project snapshot is missing project_path.")
        return Path(raw_path)


def _path_updated_at(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
