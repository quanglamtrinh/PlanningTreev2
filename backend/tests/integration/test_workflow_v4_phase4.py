from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.errors import WorkflowContextStaleError
from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.routes import workflow_v4 as workflow_v4_route_module
from backend.services import planningtree_workspace
from backend.streaming.sse_broker import GlobalEventBroker


class _StreamingTestRequest:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._is_disconnected = False
        self.headers: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return self._is_disconnected

    def disconnect(self) -> None:
        self._is_disconnected = True


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


async def _read_stream_chunk(response: Any, *, timeout_sec: float = 1.0) -> str:
    return await asyncio.wait_for(anext(response.body_iterator), timeout=timeout_sec)


def _parse_sse_chunk(chunk: str) -> dict[str, Any]:
    data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    return json.loads(data_line[len("data: ") :])


async def _read_sse_payload(response: Any, *, timeout_sec: float = 1.0) -> dict[str, Any]:
    while True:
        chunk = await _read_stream_chunk(response, timeout_sec=timeout_sec)
        if chunk.lstrip().startswith(":"):
            continue
        return _parse_sse_chunk(chunk)


async def _close_stream(response: Any, request: _StreamingTestRequest) -> None:
    request.disconnect()
    iterator = response.body_iterator
    if hasattr(iterator, "aclose"):
        await iterator.aclose()


def _project_with_confirmed_docs(client: TestClient, workspace_root: Path) -> tuple[str, str, Path]:
    snapshot = client.app.state.project_service.attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, node_id)
    assert node_dir is not None
    _write_confirmed_docs(node_dir, revision=2, frame_text="Frame v2", spec_text="Spec v2")
    return project_id, node_id, node_dir


def _write_confirmed_docs(node_dir: Path, *, revision: int, frame_text: str, spec_text: str) -> None:
    (node_dir / "frame.md").write_text(frame_text, encoding="utf-8")
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "confirmed_revision": revision,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": frame_text,
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (node_dir / "spec.meta.json").write_text(
        json.dumps(
            {
                "source_frame_revision": revision,
                "confirmed_at": "2026-04-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _install_binding_service_with_publisher(client: TestClient, manager: Any) -> None:
    app = client.app
    app.state.workflow_thread_binding_service_v2 = ThreadBindingServiceV2(
        repository=app.state.workflow_state_repository_v2,
        context_builder=WorkflowContextBuilderV2(app.state.storage),
        session_manager=manager,
        event_publisher=WorkflowEventPublisherV2(app.state.workflow_event_broker),
    )


def test_v4_workflow_state_returns_direct_canonical_default(client, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(client, workspace_root)

    response = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state")

    assert response.status_code == 200
    payload = response.json()
    assert "ok" not in payload
    assert "data" not in payload
    assert payload["schemaVersion"] == 1
    assert payload["projectId"] == project_id
    assert payload["nodeId"] == node_id
    assert payload["phase"] == "ready_for_execution"
    assert payload["version"] == 0
    assert payload["threads"] == {
        "askPlanning": None,
        "execution": None,
        "audit": None,
        "packageReview": None,
    }
    assert payload["decisions"] == {"execution": None, "audit": None}
    assert payload["context"]["stale"] is False
    assert payload["allowedActions"] == ["start_execution"]


def test_v4_workflow_state_read_through_converts_legacy_v3_phase(client, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(client, workspace_root)
    client.app.state.storage.workflow_state_store.write_state(
        project_id,
        node_id,
        {
            "nodeId": node_id,
            "workflowPhase": "audit_decision_pending",
            "reviewThreadId": "review-thread-1",
            "currentAuditDecision": {
                "status": "current",
                "sourceReviewCycleId": "cycle-1",
                "reviewCommitSha": "sha-review",
                "finalReviewText": "review text",
            },
        },
    )

    response = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/workflow-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "review_pending"
    assert payload["threads"]["audit"] == "review-thread-1"
    assert payload["decisions"]["audit"]["reviewCommitSha"] == "sha-review"
    assert payload["allowedActions"] == ["improve_in_execution", "mark_done_from_audit"]


@pytest.mark.anyio
async def test_v4_workflow_events_filter_and_adapt_legacy_updates(client, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(client, workspace_root)
    broker = GlobalEventBroker()
    client.app.state.workflow_event_broker = broker

    request = _StreamingTestRequest(client.app)
    response = await workflow_v4_route_module.workflow_events_v4(request, project_id)
    try:
        broker.publish(
            {
                "eventId": "evt-ignore",
                "projectId": "other-project",
                "nodeId": node_id,
                "type": "node.workflow.updated",
            }
        )
        broker.publish(
            {
                "eventId": "evt-detail",
                "projectId": project_id,
                "nodeId": node_id,
                "type": "node.detail.invalidate",
            }
        )
        broker.publish(
            {
                "eventId": "evt-legacy",
                "projectId": project_id,
                "nodeId": node_id,
                "occurredAt": "2026-04-24T00:00:00Z",
                "type": "node.workflow.updated",
            }
        )

        payload = await _read_sse_payload(response)
        assert payload["eventId"] == "evt-legacy"
        assert payload["projectId"] == project_id
        assert payload["nodeId"] == node_id
        assert payload["type"] == "workflow/state_changed"
        assert payload["phase"] == "ready_for_execution"
        assert payload["version"] == 0
        assert "channel" not in payload
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v4_workflow_events_pass_native_v2_events(client, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(client, workspace_root)
    broker = GlobalEventBroker()
    client.app.state.workflow_event_broker = broker

    request = _StreamingTestRequest(client.app)
    response = await workflow_v4_route_module.workflow_events_v4(request, project_id)
    try:
        broker.publish(
            {
                "eventId": "workflow-evt-1",
                "projectId": project_id,
                "nodeId": node_id,
                "occurredAt": "2026-04-24T00:00:00Z",
                "type": "workflow/context_stale",
                "phase": "ready_for_execution",
                "version": 1,
                "details": {"reason": "test"},
            }
        )

        payload = await _read_sse_payload(response)
        assert payload["type"] == "workflow/context_stale"
        assert payload["eventId"] == "workflow-evt-1"
        assert payload["details"] == {"reason": "test"}
    finally:
        await _close_stream(response, request)


def test_ensure_thread_publishes_state_changed_and_replay_does_not_republish(client, workspace_root) -> None:
    _install_binding_service_with_publisher(client, FakeSessionManager())
    project_id, node_id, _ = _project_with_confirmed_docs(client, workspace_root)
    published: list[dict[str, Any]] = []
    broker = client.app.state.workflow_event_broker
    original_publish = broker.publish

    def capture_publish(event: dict[str, Any]) -> None:
        published.append(event)
        original_publish(event)

    broker.publish = capture_publish

    try:
        payload = {"idempotencyKey": "ensure-thread:publish"}
        response = client.post(
            f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
            json=payload,
        )
        replay = client.post(
            f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
            json=payload,
        )
    finally:
        broker.publish = original_publish

    assert response.status_code == 200
    assert replay.status_code == 200
    assert [event["type"] for event in published] == ["workflow/state_changed"]
    assert published[0]["projectId"] == project_id
    assert published[0]["nodeId"] == node_id
    assert published[0]["phase"] == "ready_for_execution"
    assert published[0]["version"] == response.json()["workflowState"]["version"]


def test_ensure_thread_context_stale_publishes_context_stale(client, workspace_root) -> None:
    _install_binding_service_with_publisher(client, FakeSessionManager())
    project_id, node_id, node_dir = _project_with_confirmed_docs(client, workspace_root)
    published: list[dict[str, Any]] = []
    broker = client.app.state.workflow_event_broker
    original_publish = broker.publish

    def capture_publish(event: dict[str, Any]) -> None:
        published.append(event)
        original_publish(event)

    broker.publish = capture_publish

    try:
        response = client.post(
            f"/v4/projects/{project_id}/nodes/{node_id}/threads/execution/ensure",
            json={"idempotencyKey": "ensure-thread:first"},
        )
        assert response.status_code == 200
        _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")

        with pytest.raises(WorkflowContextStaleError):
            client.app.state.workflow_thread_binding_service_v2.ensure_thread(
                project_id=project_id,
                node_id=node_id,
                role="execution",
                idempotency_key="ensure-thread:stale",
            )
    finally:
        broker.publish = original_publish

    assert [event["type"] for event in published] == [
        "workflow/state_changed",
        "workflow/context_stale",
    ]
    assert published[1]["details"]["role"] == "execution"
    assert "context packet changed" in published[1]["details"]["reason"]
