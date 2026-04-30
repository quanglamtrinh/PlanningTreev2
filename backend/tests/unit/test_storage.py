from __future__ import annotations

from backend.config.app_config import build_app_paths
from backend.storage.storage import Storage


def test_storage_does_not_delete_projects_root_on_startup(data_root) -> None:
    paths = build_app_paths(data_root)
    existing_project_dir = paths.projects_root / "existing-project"
    existing_project_dir.mkdir(parents=True)
    (existing_project_dir / "meta.json").write_text("{}", encoding="utf-8")

    storage = Storage(paths)

    assert existing_project_dir.exists()
    assert storage.workspace_store.read() == {"entries": []}
