from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from backend.ai.chat_prompt_builder import (
    build_child_activation_prompt,
    build_local_review_prompt,
    build_package_review_prompt,
)
from backend.ai.integration_rollup_prompt_builder import build_rollup_prompt_from_storage
from backend.services import planningtree_workspace
from backend.services.node_detail_service import FRAME_META_FILE, SPEC_META_FILE
from backend.services.project_service import ProjectService


def test_build_local_review_prompt_includes_confirmed_artifacts_and_execution_state(
    storage,
    workspace_root: Path,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, root_id)
    assert node_dir is not None

    _write_json(
        node_dir / FRAME_META_FILE,
        {
            "revision": 1,
            "confirmed_revision": 1,
            "confirmed_at": "2026-03-25T00:00:00Z",
            "confirmed_content": "# Frame\nUse the safer flow.",
        },
    )
    _write_json(
        node_dir / SPEC_META_FILE,
        {
            "source_frame_revision": 1,
            "confirmed_at": "2026-03-25T01:00:00Z",
        },
    )
    (node_dir / planningtree_workspace.SPEC_FILE_NAME).write_text(
        "# Spec\nShip the reviewed implementation.",
        encoding="utf-8",
    )
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:init",
            "head_sha": "sha256:head",
            "started_at": "2026-03-25T02:00:00Z",
            "completed_at": "2026-03-25T03:00:00Z",
        },
    )

    prompt = build_local_review_prompt(storage, project_id, root_id, "Please review the execution.")

    assert "Confirmed frame" in prompt
    assert "Use the safer flow." in prompt
    assert "Confirmed spec" in prompt
    assert "Ship the reviewed implementation." in prompt
    assert "Head SHA: sha256:head" in prompt
    assert "User message:\nPlease review the execution." in prompt


def test_build_package_review_prompt_uses_manifest_and_rollup_state(
    storage,
    workspace_root: Path,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child1_id = _add_task_child(snapshot, root_id, "Child one", "Finish the first slice")
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    root_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, root_id)
    assert root_dir is not None
    _write_json(
        root_dir / FRAME_META_FILE,
        {
            "revision": 1,
            "confirmed_revision": 1,
            "confirmed_at": "2026-03-25T00:00:00Z",
            "confirmed_content": "# Frame\nPackage around the golden path.",
        },
    )
    storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-03-25T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:child1",
                    "summary": "Child one is complete and verified.",
                    "source_node_id": child1_id,
                    "accepted_at": "2026-03-25T01:00:00Z",
                },
            ],
            "rollup": {
                "status": "accepted",
                "summary": "The package is coherent and ready.",
                "sha": "sha256:rollup",
                "accepted_at": "2026-03-25T02:00:00Z",
                "draft": {
                    "summary": None,
                    "sha": None,
                    "generated_at": None,
                },
            },
            "pending_siblings": [
                {
                    "index": 2,
                    "title": "Child two",
                    "objective": "Finish the second slice",
                    "materialized_node_id": None,
                }
            ],
        },
    )

    prompt = build_package_review_prompt(storage, project_id, root_id, "Review the package status.")

    assert "Confirmed parent frame" in prompt
    assert "Package around the golden path." in prompt
    assert "Split package:" in prompt
    assert "Child one" in prompt
    assert "Child two" in prompt
    assert "The package is coherent and ready." in prompt
    assert "User message:\nReview the package status." in prompt


def test_build_child_activation_prompt_includes_assignment_and_prior_checkpoints(
    storage,
    workspace_root: Path,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child1_id = _add_task_child(snapshot, root_id, "Child one", "Finish the first slice")
    child2_id = _add_task_child(snapshot, root_id, "Child two", "Finish the second slice")
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-03-25T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:child1",
                    "summary": "Child one delivered the first milestone.",
                    "source_node_id": child1_id,
                    "accepted_at": "2026-03-25T01:00:00Z",
                },
            ],
            "rollup": {
                "status": "pending",
                "summary": None,
                "sha": None,
                "accepted_at": None,
                "draft": {
                    "summary": None,
                    "sha": None,
                    "generated_at": None,
                },
            },
            "pending_siblings": [],
        },
    )

    prompt = build_child_activation_prompt(
        storage,
        project_id,
        child2_id,
        review_id,
        "Start shaping this child.",
    )

    assert "Child activation context:" in prompt
    assert "- Assignment: Child two" in prompt
    assert "- Objective: Finish the second slice" in prompt
    assert "Prior accepted checkpoints:" in prompt
    assert "Child one delivered the first milestone." in prompt
    assert "sha256:baseline" not in prompt
    assert "User message:\nStart shaping this child." in prompt


def test_build_rollup_prompt_from_storage_uses_checkpoint_summaries_and_json_contract(
    storage,
    workspace_root: Path,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child1_id = _add_task_child(snapshot, root_id, "Child one", "Finish the first slice")
    child2_id = _add_task_child(snapshot, root_id, "Child two", "Finish the second slice")
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-03-25T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:child1",
                    "summary": "Child one completed the first milestone.",
                    "source_node_id": child1_id,
                    "accepted_at": "2026-03-25T01:00:00Z",
                },
                {
                    "label": "K2",
                    "sha": "sha256:child2",
                    "summary": "Child two completed the second milestone.",
                    "source_node_id": child2_id,
                    "accepted_at": "2026-03-25T02:00:00Z",
                },
            ],
            "rollup": {
                "status": "ready",
                "summary": None,
                "sha": None,
                "accepted_at": None,
                "draft": {
                    "summary": None,
                    "sha": None,
                    "generated_at": None,
                },
            },
            "pending_siblings": [],
        },
    )

    prompt = build_rollup_prompt_from_storage(storage, project_id, review_id)

    assert "Integration rollup context:" in prompt
    assert "Child one completed the first milestone." in prompt
    assert "Child two completed the second milestone." in prompt
    assert "sha256:baseline" not in prompt
    assert '{"summary": "Concise integration rollup summary."}' in prompt


def _save_snapshot(storage, project_id: str, snapshot: dict[str, object], workspace_root: Path) -> None:
    storage.project_store.save_snapshot(project_id, snapshot)
    planningtree_workspace.sync_snapshot_tree(workspace_root, snapshot)


def _add_task_child(
    snapshot: dict[str, object],
    parent_id: str,
    title: str,
    description: str,
) -> str:
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    child_id = uuid4().hex
    display_order = len(parent.get("child_ids", []))
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)
    parent.setdefault("child_ids", []).append(child_id)
    node_index[child_id] = {
        "node_id": child_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": display_order,
        "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
        "created_at": snapshot["updated_at"],
    }
    return child_id


def _add_review_node(snapshot: dict[str, object], parent_id: str) -> str:
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    review_id = uuid4().hex
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)
    parent["review_node_id"] = review_id
    node_index[review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": snapshot["updated_at"],
    }
    return review_id


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
