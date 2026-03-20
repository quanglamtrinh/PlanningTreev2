from __future__ import annotations

from backend.errors.app_errors import LegacyProjectUnsupported
from backend.storage.file_utils import atomic_write_json


def test_load_snapshot_rejects_legacy_thread_files(storage, workspace_root) -> None:
    project_service = storage.project_store
    project_id = "a" * 32
    project_dir = project_service.project_dir(project_id)
    project_dir.mkdir(parents=True)
    atomic_write_json(
        project_service.meta_path(project_id),
        {
            "id": project_id,
            "name": "Legacy",
            "root_goal": "Old runtime",
            "base_workspace_root": str(workspace_root),
            "project_workspace_root": str(workspace_root / "legacy"),
            "created_at": "2026-03-20T00:00:00Z",
            "updated_at": "2026-03-20T00:00:00Z",
        },
    )
    atomic_write_json(
        project_service.tree_path(project_id),
        {
            "schema_version": 5,
            "project": {"id": project_id},
            "tree_state": {"root_node_id": "root", "active_node_id": "root", "node_index": {}},
            "updated_at": "2026-03-20T00:00:00Z",
        },
    )
    (project_dir / "thread_state.json").write_text("{}", encoding="utf-8")

    try:
        storage.project_store.load_snapshot(project_id)
        raise AssertionError("Expected legacy project to be rejected")
    except LegacyProjectUnsupported as exc:
        assert exc.code == "legacy_project_unsupported"
