from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidRequest, WorkspaceFileNotFound
from backend.services.project_service import ProjectService
from backend.services.workspace_file_service import WorkspaceFileService
from backend.storage.storage import Storage


def _attach(storage: Storage, workspace_root: Path) -> str:
    project_service = ProjectService(storage)
    snap = project_service.attach_project_folder(str(workspace_root))
    return str(snap["project"]["id"])


def test_workspace_file_rejects_parent_traversal(storage: Storage, workspace_root: Path) -> None:
    project_id = _attach(storage, workspace_root)
    svc = WorkspaceFileService(storage)

    with pytest.raises(InvalidRequest):
        svc.get_text_file(project_id, "../outside.txt")

    with pytest.raises(InvalidRequest):
        svc.get_text_file(project_id, "safe/../../outside.txt")


def test_workspace_file_reads_utf8_file(storage: Storage, workspace_root: Path) -> None:
    project_id = _attach(storage, workspace_root)
    svc = WorkspaceFileService(storage)
    doc = workspace_root / "docs"
    doc.mkdir(parents=True)
    (doc / "hello.md").write_text("# Hi\n", encoding="utf-8")

    got = svc.get_text_file(project_id, "docs/hello.md")
    assert got["content"] == "# Hi\n"
    assert got["relative_path"] == "docs/hello.md"


def test_workspace_file_missing_returns_404(storage: Storage, workspace_root: Path) -> None:
    project_id = _attach(storage, workspace_root)
    svc = WorkspaceFileService(storage)

    with pytest.raises(WorkspaceFileNotFound):
        svc.get_text_file(project_id, "nope.md")
