from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidRequest, WorkspaceFileNotFound
from backend.services import planningtree_workspace
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
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


def test_workspace_file_resolves_root_and_node_scoped_docs(storage: Storage, workspace_root: Path) -> None:
    project_id = _attach(storage, workspace_root)
    snapshot = storage.project_store.load_snapshot(project_id)
    root_id = snapshot["tree_state"]["root_node_id"]
    snapshot = NodeService(storage, TreeService()).create_child(project_id, root_id)
    child_id = snapshot["tree_state"]["active_node_id"]
    svc = WorkspaceFileService(storage)

    svc.put_text_file(project_id, "docs/overview.md", "# Overview\n", scope="root_node")
    svc.put_text_file(project_id, "context.md", "# Context\n", scope="node", node_id=child_id)
    svc.put_text_file(project_id, "handoff.md", "# Handoff\n", scope="node", node_id=child_id)

    root_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, root_id)
    child_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, child_id)
    assert root_dir is not None
    assert child_dir is not None
    assert (root_dir / "docs" / "overview.md").read_text(encoding="utf-8") == "# Overview\n"
    assert (child_dir / "context.md").read_text(encoding="utf-8") == "# Context\n"
    assert (child_dir / "handoff.md").read_text(encoding="utf-8") == "# Handoff\n"
    assert svc.get_text_file(project_id, "docs/overview.md", scope="root_node")["content"] == "# Overview\n"
    assert svc.get_text_file(project_id, "context.md", scope="node", node_id=child_id)["content"] == "# Context\n"
