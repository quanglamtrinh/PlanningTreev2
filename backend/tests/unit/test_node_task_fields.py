from __future__ import annotations

from backend.services.node_task_fields import enrich_nodes_with_task_fields, load_task_prompt_fields
from backend.services.snapshot_view_service import SnapshotViewService
from backend.storage.storage import Storage


def create_project(project_service, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def write_invalid_task(storage: Storage, project_id: str, node_id: str) -> None:
    task_path = storage.node_store.node_dir(project_id, node_id) / "task.md"
    task_path.write_text("# Task\n\n## Title\nBroken\n\n## Title\nStill broken\n", encoding="utf-8")


def test_load_task_prompt_fields_returns_empty_values_for_invalid_task(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    write_invalid_task(storage, project_id, root_id)

    fields = load_task_prompt_fields(storage.node_store, project_id, root_id)

    assert fields == {"title": "", "description": ""}


def test_enrich_nodes_with_task_fields_uses_empty_fallback_for_invalid_task(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    write_invalid_task(storage, project_id, root_id)
    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = snapshot["tree_state"]["node_index"]

    enrich_nodes_with_task_fields(storage.node_store, project_id, node_by_id)

    assert node_by_id[root_id]["title"] == ""
    assert node_by_id[root_id]["description"] == ""


def test_snapshot_view_service_backfills_empty_task_fields_when_task_is_invalid(
    project_service,
    storage: Storage,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    write_invalid_task(storage, project_id, root_id)
    snapshot = storage.project_store.load_snapshot(project_id)

    public_snapshot = SnapshotViewService(storage.node_store).to_public_snapshot(project_id, snapshot)
    public_root = next(
        node for node in public_snapshot["tree_state"]["node_registry"] if node["node_id"] == root_id
    )

    assert public_root["title"] == ""
    assert public_root["description"] == ""
