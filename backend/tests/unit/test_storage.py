from __future__ import annotations

from backend.config.app_config import build_app_paths
from backend.storage.storage import Storage


def test_storage_purges_legacy_projects_only_once(data_root) -> None:
    paths = build_app_paths(data_root)
    legacy_project_dir = paths.projects_root / "legacy-project"
    legacy_project_dir.mkdir(parents=True)
    (legacy_project_dir / "meta.json").write_text("{}", encoding="utf-8")

    storage = Storage(paths)

    assert not paths.projects_root.exists()
    assert storage.workspace_store.legacy_projects_purged() is True

    recreated_legacy_dir = paths.projects_root / "legacy-project-2"
    recreated_legacy_dir.mkdir(parents=True)
    (recreated_legacy_dir / "meta.json").write_text("{}", encoding="utf-8")

    Storage(paths)

    assert recreated_legacy_dir.exists()
