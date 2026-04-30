from __future__ import annotations

from backend.services.execution_gating import AUDIT_ROLLUP_PACKAGE_MESSAGE_ID, audit_message_exists, package_audit_ready
from backend.services.project_service import ProjectService


def _review_fixture(storage, workspace_root):
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
    review_state = storage.workflow_domain_store.write_review(
        project_id,
        review_node_id,
        {
            "rollup": {
                "status": "accepted",
                "summary": "Looks good",
                "sha": "sha256:rollup",
                "package_review_started_at": "2026-04-24T00:00:00Z",
            }
        },
    )
    node = storage.project_store.load_snapshot(project_id)["tree_state"]["node_index"][node_id]
    return project_id, node_id, node, review_state


def test_audit_message_exists_checks_rollup_package_marker(storage, workspace_root) -> None:
    project_id, node_id, _, _ = _review_fixture(storage, workspace_root)

    assert audit_message_exists(
        storage,
        project_id,
        node_id,
        message_id=AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    ) is True


def test_package_audit_ready_accepts_rollup_package_marker(storage, workspace_root) -> None:
    project_id, _, node, review_state = _review_fixture(storage, workspace_root)

    assert package_audit_ready(storage, project_id, node, review_state) is True
