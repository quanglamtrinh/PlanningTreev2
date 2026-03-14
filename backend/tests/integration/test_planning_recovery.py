from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config.app_config import build_app_paths
from backend.main import create_app
from backend.services.project_service import ProjectService
from backend.services.thread_service import PLANNING_STALE_TURN_ERROR
from backend.storage.storage import Storage


def test_startup_reconciles_interrupted_planning_turns(data_root, workspace_root) -> None:
    storage = Storage(build_app_paths(data_root))
    project_service = ProjectService(storage)
    project_service.set_workspace_root(str(workspace_root))
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    storage.thread_store.set_planning_status(
        project_id,
        root_id,
        thread_id="planning_root",
        forked_from_node=None,
        status="active",
        active_turn_id="turn_stale",
    )

    app = create_app(data_root=data_root)
    with TestClient(app):
        planning = app.state.storage.thread_store.get_node_state(project_id, root_id)["planning"]

    assert planning["status"] == "idle"
    assert planning["active_turn_id"] is None
    assert planning["turns"][-1]["role"] == "assistant"
    assert planning["turns"][-1]["content"] == PLANNING_STALE_TURN_ERROR
