from __future__ import annotations

from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import PlanningEventBroker


class FakeThreadService:
    def ensure_planning_thread(self, project_id: str, node_id: str) -> str:
        return "planning_1"

    def set_planning_status(
        self,
        project_id: str,
        node_id: str,
        *,
        status: str | None,
        active_turn_id: str | None,
    ) -> dict[str, object]:
        return {"status": status, "active_turn_id": active_turn_id}


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def test_split_preflight_uses_peek_node_state_not_write_through_accessor(
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = SplitService(
        storage,
        tree_service,
        codex_client=object(),
        thread_service=FakeThreadService(),
        planning_event_broker=PlanningEventBroker(),
        split_timeout=5,
    )

    monkeypatch.setattr(
        storage.thread_store,
        "get_node_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("split preflight should not use write-through get_node_state")
        ),
    )
    monkeypatch.setattr(service, "_start_background_split", lambda **kwargs: None)

    response = service.split_node(project_id, root_id, "slice")

    assert response["status"] == "accepted"
