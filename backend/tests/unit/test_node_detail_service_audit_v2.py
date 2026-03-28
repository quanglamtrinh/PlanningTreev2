from __future__ import annotations

from pathlib import Path

from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService


def _create_project(storage, workspace_root: str) -> tuple[str, str]:
    snapshot = ProjectService(storage).attach_project_folder(workspace_root)
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def _find_snapshot_item(storage, project_id: str, node_id: str, item_id: str) -> dict | None:
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "audit")
    for item in snapshot.get("items", []):
        if item.get("id") == item_id:
            return item
    return None


def test_confirm_frame_writes_v2_audit_system_item(storage, workspace_root: Path, tree_service: TreeService) -> None:
    project_id, node_id = _create_project(storage, str(workspace_root))
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)

    doc_service.put_document(
        project_id,
        node_id,
        "frame",
        "# Task Title\nLogin flow\n\n# Task-Shaping Fields\n- target platform: web\n",
    )
    detail_service.bump_frame_revision(project_id, node_id)
    detail_service.confirm_frame(project_id, node_id)

    item = _find_snapshot_item(storage, project_id, node_id, "audit-record:frame")
    assert item is not None
    assert item["kind"] == "message"
    assert item["role"] == "system"
    assert "Canonical confirmed frame snapshot" in item["text"]


def test_confirm_spec_writes_v2_audit_system_item(storage, workspace_root: Path, tree_service: TreeService) -> None:
    project_id, node_id = _create_project(storage, str(workspace_root))
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)

    doc_service.put_document(
        project_id,
        node_id,
        "frame",
        "# Task Title\nLogin flow\n\n# Task-Shaping Fields\n- target platform: web\n",
    )
    detail_service.bump_frame_revision(project_id, node_id)
    detail_service.confirm_frame(project_id, node_id)
    doc_service.put_document(project_id, node_id, "spec", "# Spec\nBuild the login flow.\n")
    detail_service.confirm_spec(project_id, node_id)

    item = _find_snapshot_item(storage, project_id, node_id, "audit-record:spec")
    assert item is not None
    assert item["kind"] == "message"
    assert item["role"] == "system"
    assert "Canonical confirmed spec snapshot" in item["text"]
