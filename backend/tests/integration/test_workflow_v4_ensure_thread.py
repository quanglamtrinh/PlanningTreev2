from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.services import planningtree_workspace
from backend.session_core_v2.errors import SessionCoreError


class FakeSessionManager:
    def __init__(self) -> None:
        self.starts: list[dict[str, Any]] = []
        self.injects: list[dict[str, Any]] = []

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.starts.append(dict(payload or {}))
        return {"thread": {"id": f"thread-{len(self.starts)}"}}

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.injects.append({"threadId": thread_id, "payload": dict(payload)})
        return {"accepted": True}


class UninitializedSessionManager:
    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise SessionCoreError(
            code="ERR_SESSION_NOT_INITIALIZED",
            message="Session Core V2 is not initialized.",
            status_code=409,
            details={},
        )

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("inject should not be called when thread_start fails")


def _install_binding_service(client: TestClient, manager: Any) -> None:
    app = client.app
    app.state.workflow_thread_binding_service_v2 = ThreadBindingServiceV2(
        repository=app.state.workflow_state_repository_v2,
        context_builder=app.state.workflow_context_builder_v2,
        session_manager=manager,
    )


def _project_with_confirmed_docs(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    snapshot = client.app.state.project_service.attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.md").write_text("Confirmed frame", encoding="utf-8")
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": 2,
                "confirmed_revision": 2,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": "Confirmed frame",
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text("Confirmed spec", encoding="utf-8")
    (node_dir / "spec.meta.json").write_text(
        json.dumps({"source_frame_revision": 2, "confirmed_at": "2026-04-24T00:00:00Z"}),
        encoding="utf-8",
    )
    return project_id, node_id


def test_v4_ensure_thread_returns_direct_contract_shape(client, workspace_root) -> None:
    manager = FakeSessionManager()
    _install_binding_service(client, manager)
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={
            "idempotencyKey": "ensure-thread:route",
            "model": "gpt-5.4",
            "modelProvider": "openai",
            "forceRebase": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "ok" not in payload
    assert "data" not in payload
    assert payload["binding"]["projectId"] == project_id
    assert payload["binding"]["nodeId"] == node_id
    assert payload["binding"]["role"] == "execution"
    assert payload["binding"]["threadId"] == "thread-1"
    assert payload["workflowState"]["threads"]["execution"] == "thread-1"
    assert len(manager.injects) == 1


def test_v4_ensure_thread_rejects_invalid_role(client) -> None:
    response = client.post(
        "/v4/projects/p1/nodes/n1/threads/not_a_role/ensure",
        json={"idempotencyKey": "ensure-thread:invalid-role"},
    )

    assert response.status_code in {400, 422}


def test_v4_ensure_thread_returns_session_not_initialized_error(client, workspace_root) -> None:
    _install_binding_service(client, UninitializedSessionManager())
    project_id, node_id = _project_with_confirmed_docs(client, workspace_root)

    response = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
        json={"idempotencyKey": "ensure-thread:uninitialized"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "ERR_SESSION_NOT_INITIALIZED"
    assert payload["message"] == "Session Core V2 is not initialized."


def test_session_v4_routes_remain_workflow_business_free(client) -> None:
    session_routes = [
        route for route in client.app.routes if getattr(route, "path", "").startswith("/v4/session")
    ]

    assert session_routes
    assert all(route.endpoint.__module__ == "backend.routes.session_v4" for route in session_routes)
    assert not any("/projects/{projectId}/nodes/{nodeId}" in route.path for route in session_routes)
