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


def _seed_execution_user_input_pending(
    client: TestClient,
    project_id: str,
    node_id: str,
    *,
    thread_id: str,
    request_id: str = "req-1",
) -> None:
    storage = client.app.state.storage
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "execution")
    snapshot["threadId"] = thread_id
    snapshot["processingState"] = "waiting_user_input"
    snapshot["activeTurnId"] = "turn-1"
    snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
    snapshot["items"].append(
        {
            "id": "input-1",
            "kind": "userInput",
            "threadId": thread_id,
            "turnId": "turn-1",
            "sequence": 99,
            "createdAt": "2026-04-01T10:02:00Z",
            "updatedAt": "2026-04-01T10:02:00Z",
            "status": "requested",
            "source": "upstream",
            "tone": "info",
            "metadata": {},
            "requestId": request_id,
            "title": "Need confirmation",
            "questions": [
                {
                    "id": "q1",
                    "header": "Choice",
                    "prompt": "Pick one",
                    "inputType": "single_select",
                    "options": [{"label": "Option A", "description": "A"}],
                }
            ],
            "answers": [],
            "requestedAt": "2026-04-01T10:02:00Z",
            "resolvedAt": None,
        }
    )
    snapshot["pendingRequests"] = [
        {
            "requestId": request_id,
            "itemId": "input-1",
            "threadId": thread_id,
            "turnId": "turn-1",
            "status": "requested",
            "createdAt": "2026-04-01T10:02:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", snapshot)


def _seed_execution_plan_ready(
    client: TestClient,
    project_id: str,
    node_id: str,
    *,
    thread_id: str,
    plan_item_id: str = "plan-1",
    revision: int = 50,
) -> None:
    storage = client.app.state.storage
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "execution")
    snapshot["threadId"] = thread_id
    snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
    snapshot["items"].append(
        {
            "id": plan_item_id,
            "kind": "plan",
            "threadId": thread_id,
            "turnId": "turn-2",
            "sequence": revision,
            "createdAt": "2026-04-01T10:03:00Z",
            "updatedAt": "2026-04-01T10:03:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "title": "Execution plan",
            "text": "Follow this plan",
            "steps": [{"id": "s1", "text": "Implement", "status": "completed"}],
        }
    )
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", snapshot)


def test_v3_execution_snapshot_by_id_returns_wrapped_snapshot(client: TestClient, workspace_root) -> None:
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


def test_v3_execution_resolve_user_input_by_id_updates_snapshot_and_signal(
    client: TestClient, workspace_root
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    _seed_execution_user_input_pending(client, project_id, node_id, thread_id=thread_id)
    storage = client.app.state.storage

    def _fake_resolve_user_input(
        *,
        project_id: str,
        node_id: str,
        thread_role: str,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, thread_role)
        snapshot["processingState"] = "idle"
        snapshot["activeTurnId"] = None
        snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
        for pending in snapshot.get("pendingRequests", []):
            if str(pending.get("requestId") or "") != request_id:
                continue
            pending["status"] = "answered"
            pending["answers"] = answers
            pending["submittedAt"] = "2026-04-01T10:02:30Z"
            pending["resolvedAt"] = "2026-04-01T10:02:31Z"
        for item in snapshot.get("items", []):
            if str(item.get("kind") or "") != "userInput":
                continue
            if str(item.get("requestId") or "") != request_id:
                continue
            item["status"] = "answered"
            item["answers"] = answers
            item["resolvedAt"] = "2026-04-01T10:02:31Z"
            item["updatedAt"] = "2026-04-01T10:02:31Z"
        storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, thread_role, snapshot)
        return {
            "requestId": request_id,
            "itemId": "input-1",
            "threadId": thread_id,
            "turnId": "turn-1",
            "status": "answer_submitted",
            "answers": answers,
            "submittedAt": "2026-04-01T10:02:30Z",
        }

    client.app.state.thread_runtime_service_v2.resolve_user_input = _fake_resolve_user_input

    resolve_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/requests/req-1/resolve",
        params={"node_id": node_id},
        json={"answers": [{"questionId": "q1", "value": "Option A", "label": "Option A"}]},
    )
    assert resolve_response.status_code == 200
    resolve_payload = resolve_response.json()
    assert resolve_payload["ok"] is True
    assert resolve_payload["data"]["status"] == "answer_submitted"
    assert resolve_payload["data"]["requestId"] == "req-1"

    snapshot_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    snapshot_v3 = snapshot_payload["data"]["snapshot"]
    assert snapshot_v3["processingState"] == "idle"
    assert snapshot_v3["uiSignals"]["activeUserInputRequests"][0]["status"] == "answered"
    user_input_item = next(item for item in snapshot_v3["items"] if item["id"] == "input-1")
    assert user_input_item["kind"] == "userInput"
    assert user_input_item["status"] == "answered"
    assert user_input_item["answers"] == [{"questionId": "q1", "value": "Option A", "label": "Option A"}]


def test_v3_execution_plan_actions_by_id_validate_stale_and_dispatch_followup(
    client: TestClient, workspace_root
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    _seed_execution_plan_ready(
        client,
        project_id,
        node_id,
        thread_id=thread_id,
        plan_item_id="plan-1",
        revision=50,
    )

    captured: dict[str, Any] = {}

    def _fake_start_execution_followup(
        project_id_arg: str,
        node_id_arg: str,
        *,
        idempotency_key: str,
        text: str,
    ) -> dict[str, Any]:
        captured["projectId"] = project_id_arg
        captured["nodeId"] = node_id_arg
        captured["idempotencyKey"] = idempotency_key
        captured["text"] = text
        return {
            "accepted": True,
            "threadId": thread_id,
            "turnId": "turn-followup-1",
            "snapshotVersion": 77,
        }

    client.app.state.execution_audit_workflow_service_v2.start_execution_followup = (
        _fake_start_execution_followup
    )

    ok_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions",
        params={"node_id": node_id},
        json={
            "action": "implement_plan",
            "planItemId": "plan-1",
            "revision": 50,
        },
    )
    assert ok_response.status_code == 200
    ok_payload = ok_response.json()
    assert ok_payload["ok"] is True
    assert ok_payload["data"]["action"] == "implement_plan"
    assert ok_payload["data"]["planItemId"] == "plan-1"
    assert ok_payload["data"]["revision"] == 50
    assert captured["projectId"] == project_id
    assert captured["nodeId"] == node_id
    assert captured["text"] == "Implement this plan."

    stale_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions",
        params={"node_id": node_id},
        json={
            "action": "send_changes",
            "planItemId": "plan-1",
            "revision": 49,
        },
    )
    assert stale_response.status_code == 400
    stale_payload = stale_response.json()
    assert stale_payload["ok"] is False
    assert stale_payload["error"]["code"] == "invalid_request"


@pytest.mark.anyio
async def test_v3_execution_stream_emits_snapshot_and_incremental_events(client: TestClient, workspace_root) -> None:
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
