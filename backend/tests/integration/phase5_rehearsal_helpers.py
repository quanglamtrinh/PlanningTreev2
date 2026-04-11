from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now


def _set_phase5_codex_client(app, codex_client: object) -> None:
    app.state.codex_client = codex_client
    app.state.chat_service._codex_client = codex_client
    app.state.thread_lineage_service._codex_client = codex_client
    thread_query_service_v3 = getattr(app.state, "thread_query_service_v3", None)
    if thread_query_service_v3 is not None:
        thread_query_service_v3._codex_client = codex_client
    thread_runtime_service_v3 = getattr(app.state, "thread_runtime_service_v3", None)
    if thread_runtime_service_v3 is not None:
        thread_runtime_service_v3._codex_client = codex_client
    app.state.finish_task_service._codex_client = codex_client
    app.state.review_service._codex_client = codex_client
    workflow_service = getattr(app.state, "execution_audit_workflow_service", None)
    if workflow_service is not None:
        workflow_service._codex_client = codex_client


def _change_kind_to_change_type(kind: str) -> str:
    if kind == "add":
        return "created"
    if kind == "delete":
        return "deleted"
    return "updated"


def _assert_file_change_item_strict(item: dict[str, object]) -> None:
    assert str(item.get("toolType") or "") == "fileChange"
    changes = item.get("changes")
    output_files = item.get("outputFiles")
    assert isinstance(changes, list)
    assert isinstance(output_files, list)
    assert len(changes) > 0
    assert len(output_files) > 0

    normalized_changes: list[dict[str, object]] = []
    for raw_change in changes:
        assert isinstance(raw_change, dict)
        path = str(raw_change.get("path") or "").strip()
        kind = str(raw_change.get("kind") or "").strip().lower()
        if kind not in {"add", "modify", "delete"}:
            kind = "modify"
        summary = str(raw_change.get("summary") or "").strip() or None
        diff_text = str(raw_change.get("diff") or "").strip() or None
        assert path
        normalized_changes.append(
            {
                "path": path,
                "kind": kind,
                "summary": summary,
                "diff": diff_text,
            }
        )

    expected_output_files: list[dict[str, object]] = []
    for change in normalized_changes:
        entry: dict[str, object] = {
            "path": change["path"],
            "changeType": _change_kind_to_change_type(str(change["kind"])),
            "summary": change["summary"],
        }
        if isinstance(change.get("diff"), str) and str(change.get("diff")).strip():
            entry["diff"] = str(change["diff"])
        expected_output_files.append(entry)

    assert output_files == expected_output_files
    assert normalized_changes == [
        {
            "path": "final.txt",
            "kind": "modify",
            "summary": "final",
            "diff": None,
        }
    ]


def _setup_project(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    response = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    payload = response.json()
    return payload["project"]["id"], payload["tree_state"]["root_node_id"]


def _confirm_spec(storage, project_id: str, node_id: str) -> None:
    detail_service = NodeDetailService(storage, TreeService())
    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "audit",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "audit",
            "threadId": f"audit-thread-{node_id}",
        },
    )
    snapshot = storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None
    frame_path = node_dir / "frame.md"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text("# Task Title\nTask\n\n# Objective\nDo it\n", encoding="utf-8")
    detail_service.confirm_frame(project_id, node_id)
    node_dir = planningtree_workspace.resolve_node_dir(project_path, storage.project_store.load_snapshot(project_id), node_id)
    assert node_dir is not None
    spec_path = node_dir / "spec.md"
    spec_path.write_text("# Spec\nImplement it\n", encoding="utf-8")
    detail_service.confirm_spec(project_id, node_id)
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snapshot)


def _do_lazy_split(storage, project_id: str, node_id: str) -> tuple[str, str]:
    from backend.services.workspace_sha import compute_workspace_sha

    tree_service = TreeService()
    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = tree_service.node_index(snapshot)
    parent = node_by_id[node_id]
    now = iso_now()
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)

    first_child_id = uuid4().hex
    snapshot["tree_state"]["node_index"][first_child_id] = {
        "node_id": first_child_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Subtask 1",
        "description": "Do subtask 1.",
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.1",
        "created_at": now,
    }
    parent.setdefault("child_ids", []).append(first_child_id)

    review_node_id = uuid4().hex
    snapshot["tree_state"]["node_index"][review_node_id] = {
        "node_id": review_node_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 1,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": now,
    }
    parent["review_node_id"] = review_node_id
    if parent.get("status") in {"ready", "in_progress"}:
        parent["status"] = "draft"
    snapshot["tree_state"]["active_node_id"] = first_child_id
    snapshot["updated_at"] = now
    storage.project_store.save_snapshot(project_id, snapshot)

    workspace_root = Path(snapshot["project"]["project_path"])
    storage.review_state_store.write_state(
        project_id,
        review_node_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": compute_workspace_sha(workspace_root),
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": now,
                }
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )
    planningtree_workspace.sync_snapshot_tree(workspace_root, snapshot)
    return first_child_id, review_node_id
