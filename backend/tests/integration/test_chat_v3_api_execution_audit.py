from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.routes import workflow_v3 as workflow_v3_route_module


class _StreamingTestRequest:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._is_disconnected = False

    async def is_disconnected(self) -> bool:
        return self._is_disconnected

    def disconnect(self) -> None:
        self._is_disconnected = True


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


def _setup_project(client: TestClient, workspace_root) -> tuple[str, str]:
    response = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    payload = response.json()
    return payload["project"]["id"], payload["tree_state"]["root_node_id"]


def _seed_execution_thread(client: TestClient, project_id: str, node_id: str) -> str:
    storage = client.app.state.storage
    thread_id = "exec-thread-v3-1"

    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "execution",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": thread_id,
            "forkReason": "execution_bootstrap",
            "lineageRootThreadId": thread_id,
        },
    )

    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "execution")
    snapshot["threadId"] = thread_id
    snapshot["processingState"] = "idle"
    snapshot["snapshotVersion"] = 1
    snapshot["items"] = [
        {
            "id": "msg-1",
            "kind": "message",
            "threadId": thread_id,
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-01T10:00:00Z",
            "updatedAt": "2026-04-01T10:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "Initial execution summary",
            "format": "markdown",
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", snapshot)

    workflow_state = storage.workflow_state_store.default_state(node_id)
    workflow_state["executionThreadId"] = thread_id
    workflow_state["auditLineageThreadId"] = "audit-lineage-v3-1"
    storage.workflow_state_store.write_state(project_id, node_id, workflow_state)

    return thread_id


def test_v3_execution_snapshot_by_id_returns_wrapped_snapshot(client: TestClient, workspace_root) -> None:
    client.app.state.execution_audit_uiux_v3_backend_enabled = True
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    snapshot = payload["data"]["snapshot"]
    assert snapshot["lane"] == "execution"
    assert snapshot["threadId"] == thread_id
    assert snapshot["items"][0]["kind"] == "message"
    assert snapshot["uiSignals"]["planReady"] == {
        "planItemId": None,
        "revision": None,
        "ready": False,
        "failed": False,
    }


@pytest.mark.anyio
async def test_v3_execution_stream_emits_snapshot_and_incremental_events(client: TestClient, workspace_root) -> None:
    client.app.state.execution_audit_uiux_v3_backend_enabled = True
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.thread_events_by_id_v3(
        request,
        project_id,
        thread_id,
        node_id=node_id,
        after_snapshot_version=1,
    )

    try:
        first_payload = await _read_sse_payload(response)
        assert first_payload["type"] == event_types.THREAD_SNAPSHOT_V3
        assert first_payload["payload"]["snapshot"]["threadId"] == thread_id
        first_snapshot_version = int(first_payload.get("snapshotVersion") or 0)

        envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=max(1, first_snapshot_version + 1),
            event_type=event_types.CONVERSATION_ITEM_UPSERT,
            payload={
                "item": {
                    "id": "msg-2",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:01:00Z",
                    "updatedAt": "2026-04-01T10:01:00Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Incremental execution note",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v2.publish(
            project_id,
            node_id,
            envelope,
            thread_role="execution",
        )

        incremental_payload = await _read_sse_payload(response)
        assert incremental_payload["type"] == event_types.CONVERSATION_ITEM_UPSERT_V3
        assert incremental_payload["payload"]["item"]["id"] == "msg-2"
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_execution_stream_reconnect_by_version_and_guard(client: TestClient, workspace_root) -> None:
    client.app.state.execution_audit_uiux_v3_backend_enabled = True
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    storage = client.app.state.storage

    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "execution")
    snapshot["snapshotVersion"] = 2
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", snapshot)

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.thread_events_by_id_v3(
        request,
        project_id,
        thread_id,
        node_id=node_id,
        after_snapshot_version=2,
    )

    try:
        payload = await _read_sse_payload(response)
        assert payload["type"] == event_types.THREAD_SNAPSHOT_V3
        assert int(payload["snapshotVersion"]) >= 2
    finally:
        await _close_stream(response, request)

    mismatch_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/events",
        params={"node_id": node_id, "after_snapshot_version": 999},
    )
    assert mismatch_response.status_code == 409
    mismatch_payload = mismatch_response.json()
    assert mismatch_payload["ok"] is False
    assert mismatch_payload["error"]["code"] == "conversation_stream_mismatch"
