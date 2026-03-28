from __future__ import annotations

from backend.conversation.domain.types import default_thread_snapshot, next_snapshot_version
from backend.services.execution_gating import (
    AUDIT_FRAME_RECORD_MESSAGE_ID,
    AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    audit_message_exists,
    package_audit_ready,
)
from backend.services.project_service import ProjectService


def test_audit_message_exists_checks_v2_snapshot_first(storage, workspace_root) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]

    audit_snapshot = default_thread_snapshot(project_id, node_id, "audit")
    audit_snapshot["threadId"] = "audit-thread-1"
    audit_snapshot["items"] = [
        {
            "id": AUDIT_FRAME_RECORD_MESSAGE_ID,
            "kind": "message",
            "threadId": "audit-thread-1",
            "turnId": None,
            "sequence": 1,
            "createdAt": audit_snapshot["createdAt"],
            "updatedAt": audit_snapshot["updatedAt"],
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {},
            "role": "system",
            "text": "Canonical confirmed frame snapshot",
            "format": "markdown",
        }
    ]
    audit_snapshot["snapshotVersion"] = next_snapshot_version(audit_snapshot)
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "audit", audit_snapshot)

    assert audit_message_exists(
        storage,
        project_id,
        node_id,
        message_id=AUDIT_FRAME_RECORD_MESSAGE_ID,
    ) is True


def test_package_audit_ready_accepts_v2_rollup_marker(storage, workspace_root) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    review_node_id = "review-node-1"

    internal = storage.project_store.load_snapshot(project_id)
    internal["tree_state"]["node_index"][review_node_id] = {
        "node_id": review_node_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.R",
        "created_at": internal["updated_at"],
    }
    internal["tree_state"]["node_index"][node_id]["review_node_id"] = review_node_id
    storage.project_store.save_snapshot(project_id, internal)

    audit_snapshot = default_thread_snapshot(project_id, node_id, "audit")
    audit_snapshot["threadId"] = "audit-thread-1"
    audit_snapshot["items"] = [
        {
            "id": AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
            "kind": "message",
            "threadId": "audit-thread-1",
            "turnId": None,
            "sequence": 1,
            "createdAt": audit_snapshot["createdAt"],
            "updatedAt": audit_snapshot["updatedAt"],
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {},
            "role": "system",
            "text": "Rollup Package",
            "format": "markdown",
        }
    ]
    audit_snapshot["snapshotVersion"] = next_snapshot_version(audit_snapshot)
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "audit", audit_snapshot)

    review_state = {
        "rollup": {
            "status": "accepted",
            "summary": "Looks good",
            "sha": "sha256:rollup",
        }
    }
    node = storage.project_store.load_snapshot(project_id)["tree_state"]["node_index"][node_id]

    assert package_audit_ready(storage, project_id, node, review_state) is True
