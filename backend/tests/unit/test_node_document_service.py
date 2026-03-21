from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import InvalidRequest
from backend.services.node_document_service import NodeDocumentService
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.services.tree_service import TreeService
from backend.tests.unit.test_split_service import FakeCodexClient, wait_for_terminal_status


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def test_fresh_root_documents_read_as_empty(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)

    frame = service.get_document(snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"], "frame")
    spec = service.get_document(snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"], "spec")

    assert frame["content"] == ""
    assert spec["content"] == ""
    assert frame["updated_at"] is not None
    assert spec["updated_at"] is not None


def test_put_document_writes_to_expected_markdown_file(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    response = service.put_document(project_id, root_id, "frame", "# Hello")

    frame_path = workspace_root / ".planningtree" / "root" / "1 workspace" / "frame.md"
    assert response["content"] == "# Hello"
    assert frame_path.read_text(encoding="utf-8") == "# Hello"


def test_missing_projection_is_repaired_before_document_read(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)
    root_dir = workspace_root / ".planningtree" / "root" / "1 workspace"

    (root_dir / "frame.md").unlink()
    (root_dir / "spec.md").unlink()
    (workspace_root / ".planningtree" / "root").rename(workspace_root / ".planningtree" / "root.bak")

    document = service.get_document(snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"], "frame")

    repaired_root = workspace_root / ".planningtree" / "root" / "1 workspace"
    assert document["content"] == ""
    assert repaired_root.is_dir()
    assert (repaired_root / "frame.md").exists()
    assert (repaired_root / "spec.md").exists()


def test_invalid_document_kind_is_rejected(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)

    with pytest.raises(InvalidRequest):
        service.get_document(snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"], "notes")


def test_document_lookup_survives_title_rename(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    tree_service = TreeService()
    node_service = NodeService(storage, tree_service)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    service.put_document(project_id, root_id, "frame", "keep this")
    node_service.update_node(project_id, root_id, title="Renamed Root")

    frame = service.get_document(project_id, root_id, "frame")

    assert frame["content"] == "keep this"
    assert (workspace_root / ".planningtree" / "root" / "1 Renamed Root" / "frame.md").read_text(
        encoding="utf-8"
    ) == "keep this"


def test_reset_to_root_removes_descendant_documents_but_keeps_root(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    tree_service = TreeService()
    node_service = NodeService(storage, tree_service)
    service = NodeDocumentService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    child_snapshot = node_service.create_child(project_id, root_id)
    child_id = child_snapshot["tree_state"]["active_node_id"]
    service.put_document(project_id, root_id, "frame", "root content")
    service.put_document(project_id, child_id, "frame", "child content")

    project_service.reset_to_root(project_id)

    root_dir = workspace_root / ".planningtree" / "root" / "1 workspace"
    child_dir = root_dir / "1.1 New Node"
    assert root_dir.is_dir()
    assert root_dir.joinpath("frame.md").read_text(encoding="utf-8") == "root content"
    assert not child_dir.exists()


def test_split_created_child_documents_are_available(
    storage,
    workspace_root: Path,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    service = NodeDocumentService(storage)
    split_service = SplitService(
        storage,
        TreeService(),
        FakeCodexClient(
            payloads=[
                {
                    "subtasks": [
                        {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts."},
                        {"id": "S2", "title": "Finish", "objective": "Finish the flow.", "why_now": "It follows."},
                    ]
                }
            ]
        ),
        split_timeout=5,
    )

    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    split_service.split_node(project_id, root_id, "workflow")
    wait_for_terminal_status(split_service, project_id)
    persisted = storage.project_store.load_snapshot(project_id)
    child_id = persisted["tree_state"]["node_index"][root_id]["child_ids"][0]

    frame = service.get_document(project_id, child_id, "frame")
    spec = service.get_document(project_id, child_id, "spec")

    assert frame["content"] == ""
    assert spec["content"] == ""
