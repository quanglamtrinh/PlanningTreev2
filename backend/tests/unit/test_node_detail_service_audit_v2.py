from __future__ import annotations

from pathlib import Path

from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService


class _NoopSystemMessageWriter:
    def upsert_system_message(self, **kwargs: object) -> dict[str, object]:
        return {}


def _create_project(storage, workspace_root: str) -> tuple[str, str]:
    snapshot = ProjectService(storage).attach_project_folder(workspace_root)
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def _seed_audit_thread_binding(storage, project_id: str, node_id: str) -> None:
    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "audit",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "audit",
            "threadId": "audit-thread-1",
        },
    )


def _find_snapshot_item(storage, project_id: str, node_id: str, item_id: str) -> dict | None:
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "audit")
    for item in snapshot.get("items", []):
        if item.get("id") == item_id:
            return item
    return None


def test_confirm_frame_writes_v2_audit_system_item(storage, workspace_root: Path, tree_service: TreeService) -> None:
    project_id, node_id = _create_project(storage, str(workspace_root))
    _seed_audit_thread_binding(storage, project_id, node_id)
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
    _seed_audit_thread_binding(storage, project_id, node_id)
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


def test_detail_state_falls_back_to_execution_state_when_latest_commit_missing(
    storage,
    workspace_root: Path,
    tree_service: TreeService,
) -> None:
    project_id, node_id = _create_project(storage, str(workspace_root))
    detail_service = NodeDetailService(
        storage,
        tree_service,
        system_message_writer=_NoopSystemMessageWriter(),
    )

    storage.execution_state_store.write_state(
        project_id,
        node_id,
        {
            "status": "completed",
            "initial_sha": "a" * 40,
            "head_sha": "b" * 40,
            "commit_message": "pt(1): legacy execution commit",
            "changed_files": [],
        },
    )

    state = detail_service.get_detail_state(project_id, node_id)

    assert state["initial_sha"] == "a" * 40
    assert state["head_sha"] == "b" * 40
    assert state["commit_message"] == "pt(1): legacy execution commit"
