from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.context_packets import PlanningTreeContextPacket
from backend.services import planningtree_workspace
from backend.services.project_service import ProjectService


def _project_with_confirmed_docs(storage: Any, workspace_root: Path) -> tuple[str, str, dict[str, Any], Path]:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.md").write_text("Confirmed frame", encoding="utf-8")
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": 3,
                "confirmed_revision": 2,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": "Confirmed frame",
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text("Confirmed spec", encoding="utf-8")
    (node_dir / "spec.meta.json").write_text(
        json.dumps(
            {
                "source_frame_revision": 2,
                "confirmed_at": "2026-04-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return project_id, node_id, snapshot, node_dir


def test_context_packet_hash_is_stable_for_dict_key_order() -> None:
    first = PlanningTreeContextPacket(
        kind="execution_context",
        projectId="p1",
        nodeId="n1",
        payload={"b": 2, "a": {"y": 2, "x": 1}},
        sourceVersions={"specVersion": 2, "frameVersion": 2, "splitManifestVersion": None},
    )
    second = PlanningTreeContextPacket(
        kind="execution_context",
        projectId="p1",
        nodeId="n1",
        payload={"a": {"x": 1, "y": 2}, "b": 2},
        sourceVersions={"splitManifestVersion": None, "frameVersion": 2, "specVersion": 2},
    )

    assert first.canonical_json() == second.canonical_json()
    assert first.packet_hash() == second.packet_hash()


def test_rendered_context_message_contains_canonical_json() -> None:
    packet = PlanningTreeContextPacket(
        kind="ask_planning_context",
        projectId="p1",
        nodeId="n1",
        payload={"z": 1},
        sourceVersions={"frameVersion": None, "specVersion": None, "splitManifestVersion": None},
    )

    rendered = packet.render_model_visible_message()

    assert packet.canonical_json() in rendered
    assert rendered.startswith('<planning_tree_context kind="ask_planning_context"')


def test_builder_produces_expected_role_kinds_and_source_versions(storage, workspace_root) -> None:
    project_id, node_id, _, _ = _project_with_confirmed_docs(storage, workspace_root)
    builder = WorkflowContextBuilderV2(storage)

    expected = {
        "ask_planning": "ask_planning_context",
        "execution": "execution_context",
        "audit": "audit_context",
        "package_review": "package_review_context",
    }
    for role, kind in expected.items():
        packet = builder.build_context_packet(project_id=project_id, node_id=node_id, role=role)  # type: ignore[arg-type]
        assert packet.kind == kind
        assert packet.source_versions == {
            "frameVersion": 2,
            "specVersion": 2,
            "splitManifestVersion": None,
        }


def test_ask_planning_child_activation_packet_kind(storage, workspace_root) -> None:
    project_id, root_id, snapshot, _ = _project_with_confirmed_docs(storage, workspace_root)
    node_index = snapshot["tree_state"]["node_index"]
    child_id = "child-1"
    review_id = "review-1"
    node_index[root_id]["review_node_id"] = review_id
    node_index[root_id]["child_ids"] = [child_id, review_id]
    node_index[child_id] = {
        "node_id": child_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child",
        "description": "",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
    }
    node_index[review_id] = {
        "node_id": review_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": 1,
        "display_order": 1,
        "hierarchical_number": "1.R",
    }
    storage.project_store.save_snapshot(project_id, snapshot)

    packet = WorkflowContextBuilderV2(storage).build_context_packet(
        project_id=project_id,
        node_id=child_id,
        role="ask_planning",
    )

    assert packet.kind == "child_activation_context"


def test_builder_includes_parent_and_current_artifact_context(storage, workspace_root) -> None:
    project_id, root_id, snapshot, root_dir = _project_with_confirmed_docs(storage, workspace_root)
    child_id = "child-context"
    sibling_id = "sibling-context"
    node_index = snapshot["tree_state"]["node_index"]
    node_index[root_id]["child_ids"] = [child_id, sibling_id]
    node_index[child_id] = {
        "node_id": child_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child Context",
        "description": "",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
    }
    node_index[sibling_id] = {
        "node_id": sibling_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Sibling Context",
        "description": "",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 1,
        "hierarchical_number": "1.2",
    }
    (root_dir / "clarify.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "confirmed_revision": 2,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "questions": [
                    {
                        "question": "Which scope?",
                        "custom_answer": "Only the selected child.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    storage.project_store.save_snapshot(project_id, snapshot)
    child_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, child_id)
    assert child_dir is not None
    (child_dir / "frame.md").write_text("Child frame", encoding="utf-8")
    (child_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": 1,
                "confirmed_revision": 1,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": "Child frame",
            }
        ),
        encoding="utf-8",
    )
    (child_dir / "spec.md").write_text("Child spec", encoding="utf-8")
    (child_dir / "spec.meta.json").write_text(
        json.dumps(
            {
                "source_frame_revision": 1,
                "confirmed_at": "2026-04-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    packet = WorkflowContextBuilderV2(storage).build_context_packet(
        project_id=project_id,
        node_id=child_id,
        role="ask_planning",
    )

    artifact_context = packet.payload["artifactContext"]
    ancestor = artifact_context["ancestorContext"][0]
    assert ancestor["node"]["node_id"] == root_id
    assert ancestor["frame"]["content"] == "Confirmed frame"
    assert ancestor["clarify"]["questions"][0]["custom_answer"] == "Only the selected child."
    assert ancestor["split"]["children"][0]["node_id"] == child_id
    assert ancestor["split"]["children"][0]["isCurrentPath"] is True
    assert ancestor["split"]["children"][1]["isCurrentPath"] is False
    assert artifact_context["currentContext"]["frame"]["content"] == "Child frame"
    assert artifact_context["currentContext"]["spec"]["content"] == "Child spec"
