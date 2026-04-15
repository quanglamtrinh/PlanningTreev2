from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.conversation.services.thread_runtime_service_v3 as thread_runtime_service_v3_module
from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.routes import workflow_v3 as workflow_v3_route_module
from backend.streaming.sse_broker import ChatEventBroker, GlobalEventBroker


class _StreamingTestRequest:
    def __init__(self, app: Any, *, headers: dict[str, str] | None = None) -> None:
        self.app = app
        self._is_disconnected = False
        self.headers = headers or {}

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


async def _assert_stream_closed(response: Any, *, timeout_sec: float = 1.0) -> None:
    with pytest.raises(StopAsyncIteration):
        await _read_stream_chunk(response, timeout_sec=timeout_sec)


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


def _set_execution_items_with_sequences(
    client: TestClient,
    project_id: str,
    node_id: str,
    *,
    thread_id: str,
    sequences: list[int],
) -> None:
    storage = client.app.state.storage
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "execution")
    snapshot["threadId"] = thread_id
    snapshot["processingState"] = "idle"
    snapshot["snapshotVersion"] = max(sequences, default=0) + 1
    snapshot["items"] = [
        {
            "id": f"msg-{sequence}",
            "kind": "message",
            "threadId": thread_id,
            "turnId": f"turn-{sequence}",
            "sequence": sequence,
            "createdAt": f"2026-04-01T10:{sequence:02d}:00Z",
            "updatedAt": f"2026-04-01T10:{sequence:02d}:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": f"message-{sequence}",
            "format": "markdown",
        }
        for sequence in sequences
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", snapshot)


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


def _stub_ask_session_reads(client: TestClient) -> None:
    storage = client.app.state.storage

    def _get_session(project_id: str, node_id: str, thread_role: str = "ask_planning") -> dict[str, Any]:
        return storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)

    client.app.state.chat_service.get_session = _get_session


def _seed_ask_thread(
    client: TestClient,
    project_id: str,
    node_id: str,
    *,
    thread_id: str = "ask-thread-v3-1",
    seed_registry: bool = True,
) -> str:
    storage = client.app.state.storage

    ask_session = storage.chat_state_store.read_session(project_id, node_id, thread_role="ask_planning")
    ask_session["thread_id"] = thread_id
    ask_session["active_turn_id"] = None
    storage.chat_state_store.write_session(project_id, node_id, ask_session, thread_role="ask_planning")

    if seed_registry:
        storage.thread_registry_store.write_entry(
            project_id,
            node_id,
            "ask_planning",
            {
                "projectId": project_id,
                "nodeId": node_id,
                "threadRole": "ask_planning",
                "threadId": thread_id,
                "forkReason": "ask_bootstrap",
                "lineageRootThreadId": thread_id,
            },
        )

    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "ask_planning")
    snapshot["threadId"] = thread_id
    snapshot["processingState"] = "idle"
    snapshot["snapshotVersion"] = 1
    snapshot["items"] = [
        {
            "id": "ask-msg-1",
            "kind": "message",
            "threadId": thread_id,
            "turnId": "ask-turn-1",
            "sequence": 1,
            "createdAt": "2026-04-01T09:00:00Z",
            "updatedAt": "2026-04-01T09:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "Initial ask summary",
            "format": "markdown",
        }
    ]
    snapshot["pendingRequests"] = []
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "ask_planning", snapshot)
    return thread_id


def _seed_audit_thread(client: TestClient, project_id: str, node_id: str, *, thread_id: str = "audit-thread-v3-1") -> str:
    storage = client.app.state.storage

    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "audit",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "audit",
            "threadId": thread_id,
            "forkReason": "local_review_thread",
            "lineageRootThreadId": thread_id,
        },
    )
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "audit")
    snapshot["threadId"] = thread_id
    snapshot["snapshotVersion"] = 1
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "audit", snapshot)

    workflow_state = storage.workflow_state_store.default_state(node_id)
    workflow_state["reviewThreadId"] = thread_id
    workflow_state["auditLineageThreadId"] = thread_id
    storage.workflow_state_store.write_state(project_id, node_id, workflow_state)
    return thread_id


def _seed_ask_user_input_pending(
    client: TestClient,
    project_id: str,
    node_id: str,
    *,
    thread_id: str,
    request_id: str = "ask-req-1",
) -> None:
    storage = client.app.state.storage
    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "ask_planning")
    snapshot["threadId"] = thread_id
    snapshot["processingState"] = "waiting_user_input"
    snapshot["activeTurnId"] = "ask-turn-1"
    snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
    snapshot["items"].append(
        {
            "id": "ask-input-1",
            "kind": "userInput",
            "threadId": thread_id,
            "turnId": "ask-turn-1",
            "sequence": 99,
            "createdAt": "2026-04-01T09:02:00Z",
            "updatedAt": "2026-04-01T09:02:00Z",
            "status": "requested",
            "source": "upstream",
            "tone": "info",
            "metadata": {},
            "requestId": request_id,
            "title": "Need clarification",
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
            "requestedAt": "2026-04-01T09:02:00Z",
            "resolvedAt": None,
        }
    )
    snapshot["pendingRequests"] = [
        {
            "requestId": request_id,
            "itemId": "ask-input-1",
            "threadId": thread_id,
            "turnId": "ask-turn-1",
            "status": "requested",
            "createdAt": "2026-04-01T09:02:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "ask_planning", snapshot)


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
    assert snapshot["threadRole"] == "execution"
    assert "lane" not in snapshot
    assert snapshot["threadId"] == thread_id
    assert snapshot["items"][0]["kind"] == "message"
    assert snapshot["uiSignals"]["planReady"] == {
        "planItemId": None,
        "revision": None,
        "ready": False,
        "failed": False,
    }


def test_v3_execution_snapshot_by_id_live_limit_returns_tail_and_history_meta(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    _set_execution_items_with_sequences(
        client,
        project_id,
        node_id,
        thread_id=thread_id,
        sequences=[1, 2, 3, 4, 5, 6, 7],
    )

    baseline_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert baseline_response.status_code == 200
    baseline_snapshot = baseline_response.json()["data"]["snapshot"]
    assert [item["sequence"] for item in baseline_snapshot["items"]] == [1, 2, 3, 4, 5, 6, 7]
    assert "historyMeta" not in baseline_snapshot

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id, "live_limit": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    snapshot = payload["data"]["snapshot"]
    assert [item["sequence"] for item in snapshot["items"]] == [5, 6, 7]
    assert snapshot["historyMeta"] == {
        "hasOlder": True,
        "oldestVisibleSequence": 5,
        "totalItemCount": 7,
    }


def test_v3_execution_history_by_id_paginates_by_before_sequence_cursor(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    _set_execution_items_with_sequences(
        client,
        project_id,
        node_id,
        thread_id=thread_id,
        sequences=[1, 2, 3, 4, 5, 6, 7, 8],
    )

    first_page_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/history",
        params={"node_id": node_id, "limit": 3},
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()["data"]
    assert [item["sequence"] for item in first_page["items"]] == [6, 7, 8]
    assert first_page["has_more"] is True
    assert first_page["next_before_sequence"] == 6
    assert first_page["total_item_count"] == 8

    second_page_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/history",
        params={
            "node_id": node_id,
            "limit": 3,
            "before_sequence": first_page["next_before_sequence"],
        },
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()["data"]
    assert [item["sequence"] for item in second_page["items"]] == [3, 4, 5]
    assert second_page["has_more"] is True
    assert second_page["next_before_sequence"] == 3
    assert second_page["total_item_count"] == 8

    final_page_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/history",
        params={
            "node_id": node_id,
            "limit": 3,
            "before_sequence": second_page["next_before_sequence"],
        },
    )
    assert final_page_response.status_code == 200
    final_page = final_page_response.json()["data"]
    assert [item["sequence"] for item in final_page["items"]] == [1, 2]
    assert final_page["has_more"] is False
    assert final_page["next_before_sequence"] is None
    assert final_page["total_item_count"] == 8


def test_v3_ask_snapshot_by_id_returns_wrapped_snapshot(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    snapshot = payload["data"]["snapshot"]
    assert snapshot["threadRole"] == "ask_planning"
    assert "lane" not in snapshot
    assert snapshot["threadId"] == thread_id
    assert snapshot["items"][0]["kind"] == "message"


def test_v3_ask_snapshot_by_id_seeds_registry_from_legacy_session(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id, seed_registry=False)

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["snapshot"]["threadRole"] == "ask_planning"
    assert "lane" not in payload["data"]["snapshot"]

    seeded_entry = client.app.state.storage.thread_registry_store.read_entry(project_id, node_id, "ask_planning")
    assert seeded_entry["threadId"] == thread_id

def test_v3_ask_snapshot_by_id_seed_respects_bridge_disabled(client: TestClient, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "disabled")
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id, seed_registry=False)

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"

    entry = client.app.state.storage.thread_registry_store.read_entry(project_id, node_id, "ask_planning")
    assert not str(entry.get("threadId") or "").strip()


def test_v3_ask_snapshot_by_id_seed_respects_bridge_allowlist(client: TestClient, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "allowlist")
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id, seed_registry=False)

    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", "other-project")
    denied = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert denied.status_code == 400
    denied_payload = denied.json()
    assert denied_payload["ok"] is False
    assert denied_payload["error"]["code"] == "invalid_request"

    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", project_id)
    allowed = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert allowed.status_code == 200
    allowed_payload = allowed.json()
    assert allowed_payload["ok"] is True
    assert allowed_payload["data"]["snapshot"]["threadRole"] == "ask_planning"
    assert "lane" not in allowed_payload["data"]["snapshot"]


def test_v3_by_id_snapshot_rejects_thread_id_mismatch(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _seed_execution_thread(client, project_id, node_id)

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/thread-does-not-match",
        params={"node_id": node_id},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"


def test_v3_workflow_state_endpoint_calls_canonical_service(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    calls: list[tuple[str, str]] = []

    class _CanonicalWorkflowService:
        def get_workflow_state(self, project_id_arg: str, node_id_arg: str) -> dict[str, Any]:
            calls.append((project_id_arg, node_id_arg))
            return {
                "nodeId": node_id_arg,
                "workflowPhase": "idle",
                "askThreadId": None,
                "executionThreadId": None,
                "reviewThreadId": None,
                "auditLineageThreadId": None,
                "currentExecutionDecision": None,
                "currentAuditDecision": None,
                "canSendExecutionMessage": False,
                "canReviewInAudit": False,
                "canImproveInExecution": False,
                "canMarkDoneFromExecution": False,
                "canMarkDoneFromAudit": False,
                "source": "canonical",
            }

    class _LegacyWorkflowService:
        def get_workflow_state(self, *_args, **_kwargs):  # pragma: no cover - guard assertion
            raise AssertionError("Legacy workflow service alias should not be used when canonical service is present.")

    client.app.state.execution_audit_workflow_service = _CanonicalWorkflowService()

    response = client.get(f"/v3/projects/{project_id}/nodes/{node_id}/workflow-state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["source"] == "canonical"
    assert calls == [(project_id, node_id)]


def test_v3_workflow_action_endpoints_dispatch_to_canonical_service(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    calls: list[tuple[str, dict[str, Any]]] = []

    class _CanonicalWorkflowService:
        def finish_task(self, project_id_arg: str, node_id_arg: str, *, idempotency_key: str) -> dict[str, Any]:
            payload = {"projectId": project_id_arg, "nodeId": node_id_arg, "idempotencyKey": idempotency_key}
            calls.append(("finish_task", payload))
            return {"source": "canonical", "action": "finish-task", **payload}

        def mark_done_from_execution(
            self,
            project_id_arg: str,
            node_id_arg: str,
            *,
            idempotency_key: str,
            expected_workspace_hash: str,
        ) -> dict[str, Any]:
            payload = {
                "projectId": project_id_arg,
                "nodeId": node_id_arg,
                "idempotencyKey": idempotency_key,
                "expectedWorkspaceHash": expected_workspace_hash,
            }
            calls.append(("mark_done_from_execution", payload))
            return {"source": "canonical", "action": "mark-done-from-execution", **payload}

        def review_in_audit(
            self,
            project_id_arg: str,
            node_id_arg: str,
            *,
            idempotency_key: str,
            expected_workspace_hash: str,
        ) -> dict[str, Any]:
            payload = {
                "projectId": project_id_arg,
                "nodeId": node_id_arg,
                "idempotencyKey": idempotency_key,
                "expectedWorkspaceHash": expected_workspace_hash,
            }
            calls.append(("review_in_audit", payload))
            return {"source": "canonical", "action": "review-in-audit", **payload}

        def mark_done_from_audit(
            self,
            project_id_arg: str,
            node_id_arg: str,
            *,
            idempotency_key: str,
            expected_review_commit_sha: str,
        ) -> dict[str, Any]:
            payload = {
                "projectId": project_id_arg,
                "nodeId": node_id_arg,
                "idempotencyKey": idempotency_key,
                "expectedReviewCommitSha": expected_review_commit_sha,
            }
            calls.append(("mark_done_from_audit", payload))
            return {"source": "canonical", "action": "mark-done-from-audit", **payload}

        def improve_in_execution(
            self,
            project_id_arg: str,
            node_id_arg: str,
            *,
            idempotency_key: str,
            expected_review_commit_sha: str,
        ) -> dict[str, Any]:
            payload = {
                "projectId": project_id_arg,
                "nodeId": node_id_arg,
                "idempotencyKey": idempotency_key,
                "expectedReviewCommitSha": expected_review_commit_sha,
            }
            calls.append(("improve_in_execution", payload))
            return {"source": "canonical", "action": "improve-in-execution", **payload}

    class _LegacyWorkflowService:
        def __getattr__(self, _name: str):  # pragma: no cover - guard assertion
            raise AssertionError("Legacy workflow service alias should not be used when canonical service is present.")

    client.app.state.execution_audit_workflow_service = _CanonicalWorkflowService()

    finish_payload = {"idempotencyKey": "idem-finish"}
    finish_response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task",
        json=finish_payload,
    )
    assert finish_response.status_code == 200
    assert finish_response.json()["data"]["action"] == "finish-task"

    mark_exec_response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution",
        json={"idempotencyKey": "idem-mark-exec", "expectedWorkspaceHash": "sha:workspace"},
    )
    assert mark_exec_response.status_code == 200
    assert mark_exec_response.json()["data"]["action"] == "mark-done-from-execution"

    review_response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit",
        json={"idempotencyKey": "idem-review", "expectedWorkspaceHash": "sha:workspace"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["data"]["action"] == "review-in-audit"

    mark_audit_response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit",
        json={"idempotencyKey": "idem-mark-audit", "expectedReviewCommitSha": "sha:review"},
    )
    assert mark_audit_response.status_code == 200
    assert mark_audit_response.json()["data"]["action"] == "mark-done-from-audit"

    improve_response = client.post(
        f"/v3/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution",
        json={"idempotencyKey": "idem-improve", "expectedReviewCommitSha": "sha:review"},
    )
    assert improve_response.status_code == 200
    assert improve_response.json()["data"]["action"] == "improve-in-execution"

    assert [name for name, _ in calls] == [
        "finish_task",
        "mark_done_from_execution",
        "review_in_audit",
        "mark_done_from_audit",
        "improve_in_execution",
    ]


@pytest.mark.anyio
async def test_v3_workflow_events_endpoint_uses_canonical_broker_and_filters_project(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    canonical_broker = GlobalEventBroker()

    client.app.state.workflow_event_broker = canonical_broker

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.workflow_events_v3(request, project_id)
    try:
        canonical_broker.publish(
            {
                "eventId": "evt-ignore",
                "projectId": "other-project",
                "nodeId": node_id,
                "type": "node.workflow.updated",
                "payload": {"reason": "ignore"},
            }
        )
        canonical_broker.publish(
            {
                "eventId": "evt-accept",
                "projectId": project_id,
                "nodeId": node_id,
                "type": "node.workflow.updated",
                "payload": {"reason": "phase4-test"},
            }
        )
        payload = await _read_sse_payload(response)
        assert payload["eventId"] == "evt-accept"
        assert payload["projectId"] == project_id
        assert payload["nodeId"] == node_id
        assert payload["type"] == "node.workflow.updated"
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_workflow_events_endpoint_closes_lagged_subscriber_without_silent_continuation(
    client: TestClient,
    workspace_root,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    lagged_broker = GlobalEventBroker(subscriber_queue_max=1)
    client.app.state.workflow_event_broker = lagged_broker

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.workflow_events_v3(request, project_id)
    try:
        for idx in range(4):
            lagged_broker.publish(
                {
                    "eventId": f"evt-lagged-{idx}",
                    "projectId": project_id,
                    "nodeId": node_id,
                    "type": "node.workflow.updated",
                    "payload": {"reason": "lagged"},
                }
            )
        await asyncio.sleep(0)
        await _assert_stream_closed(response, timeout_sec=1.0)
    finally:
        await _close_stream(response, request)


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
        if not storage.thread_snapshot_store_v3.exists(project_id, node_id, thread_role):
            client.app.state.thread_query_service_v3.get_thread_snapshot(
                project_id,
                node_id,
                thread_role,
                publish_repairs=False,
                ensure_binding=False,
            )
        snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, thread_role)
        snapshot["processingState"] = "idle"
        snapshot["activeTurnId"] = None
        snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
        for pending in snapshot.get("uiSignals", {}).get("activeUserInputRequests", []):
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
        storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, snapshot)
        return {
            "requestId": request_id,
            "itemId": "input-1",
            "threadId": thread_id,
            "turnId": "turn-1",
            "status": "answer_submitted",
            "answers": answers,
            "submittedAt": "2026-04-01T10:02:30Z",
        }

    client.app.state.thread_runtime_service_v3.resolve_user_input = _fake_resolve_user_input

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


def test_v3_ask_turns_by_id_dispatches_to_runtime(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)
    captured: dict[str, Any] = {}

    def _fake_start_turn(
        project_id_arg: str,
        node_id_arg: str,
        thread_role: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured["projectId"] = project_id_arg
        captured["nodeId"] = node_id_arg
        captured["threadRole"] = thread_role
        captured["text"] = text
        captured["metadata"] = metadata or {}
        return {
            "accepted": True,
            "threadId": thread_id,
            "turnId": "ask-turn-next",
            "snapshotVersion": 9,
            "createdItems": [],
        }

    client.app.state.thread_runtime_service_v3.start_turn = _fake_start_turn

    response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/turns",
        params={"node_id": node_id},
        json={"text": "Ask follow-up", "metadata": {"idempotencyKey": "ask-1"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["turnId"] == "ask-turn-next"
    assert captured == {
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": "ask_planning",
        "text": "Ask follow-up",
        "metadata": {"idempotencyKey": "ask-1"},
    }


def test_v3_ask_turns_by_id_idempotent_replay_avoids_duplicate_turn_creation(
    client: TestClient,
    workspace_root,
    monkeypatch,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    endpoint = f"/v3/projects/{project_id}/threads/by-id/{thread_id}/turns"
    payload = {"text": "Ask follow-up", "metadata": {"idempotencyKey": "ask-idem-1"}}

    first = client.post(endpoint, params={"node_id": node_id}, json=payload)
    second = client.post(endpoint, params={"node_id": node_id}, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert second_data["turnId"] == first_data["turnId"]
    assert second_data["threadId"] == first_data["threadId"]

    snapshot = client.app.state.thread_query_service_v3.get_thread_snapshot(
        project_id,
        node_id,
        "ask_planning",
        publish_repairs=False,
    )
    user_messages = [
        item
        for item in snapshot.get("items", [])
        if str(item.get("kind") or "") == "message" and str(item.get("role") or "") == "user"
    ]
    assert len(user_messages) == 1


def test_v3_ask_turns_by_id_idempotency_conflict_returns_typed_409(
    client: TestClient,
    workspace_root,
    monkeypatch,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    endpoint = f"/v3/projects/{project_id}/threads/by-id/{thread_id}/turns"
    first = client.post(
        endpoint,
        params={"node_id": node_id},
        json={"text": "Ask follow-up", "metadata": {"idempotencyKey": "ask-idem-1"}},
    )
    assert first.status_code == 200

    conflict = client.post(
        endpoint,
        params={"node_id": node_id},
        json={"text": "Different ask payload", "metadata": {"idempotencyKey": "ask-idem-1"}},
    )
    assert conflict.status_code == 409
    conflict_payload = conflict.json()
    assert conflict_payload["ok"] is False
    assert conflict_payload["error"]["code"] == "ask_idempotency_payload_conflict"


def test_v3_ask_idempotency_scope_does_not_cross_reset_to_new_thread(
    client: TestClient,
    workspace_root,
    monkeypatch,
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    old_thread_id = _seed_ask_thread(client, project_id, node_id, thread_id="ask-thread-v3-old")

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    old_endpoint = f"/v3/projects/{project_id}/threads/by-id/{old_thread_id}/turns"
    first = client.post(
        old_endpoint,
        params={"node_id": node_id},
        json={"text": "Ask follow-up", "metadata": {"idempotencyKey": "ask-reset-1"}},
    )
    assert first.status_code == 200
    first_data = first.json()["data"]

    reset = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{old_thread_id}/reset",
        params={"node_id": node_id},
    )
    assert reset.status_code == 200

    new_thread_id = _seed_ask_thread(client, project_id, node_id, thread_id="ask-thread-v3-new")
    new_endpoint = f"/v3/projects/{project_id}/threads/by-id/{new_thread_id}/turns"
    second = client.post(
        new_endpoint,
        params={"node_id": node_id},
        json={"text": "Ask follow-up", "metadata": {"idempotencyKey": "ask-reset-1"}},
    )
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["threadId"] == new_thread_id
    assert second_data["turnId"] != first_data["turnId"]


def test_v3_ask_resolve_user_input_by_id_updates_snapshot_and_signal(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)
    _seed_ask_user_input_pending(client, project_id, node_id, thread_id=thread_id)
    storage = client.app.state.storage

    def _fake_resolve_user_input(
        *,
        project_id: str,
        node_id: str,
        thread_role: str,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert thread_role == "ask_planning"
        if not storage.thread_snapshot_store_v3.exists(project_id, node_id, thread_role):
            client.app.state.thread_query_service_v3.get_thread_snapshot(
                project_id,
                node_id,
                thread_role,
                publish_repairs=False,
                ensure_binding=False,
            )
        snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, thread_role)
        snapshot["processingState"] = "idle"
        snapshot["activeTurnId"] = None
        snapshot["snapshotVersion"] = int(snapshot.get("snapshotVersion") or 0) + 1
        for pending in snapshot.get("uiSignals", {}).get("activeUserInputRequests", []):
            if str(pending.get("requestId") or "") != request_id:
                continue
            pending["status"] = "answered"
            pending["answers"] = answers
            pending["submittedAt"] = "2026-04-01T09:02:30Z"
            pending["resolvedAt"] = "2026-04-01T09:02:31Z"
        for item in snapshot.get("items", []):
            if str(item.get("kind") or "") != "userInput":
                continue
            if str(item.get("requestId") or "") != request_id:
                continue
            item["status"] = "answered"
            item["answers"] = answers
            item["resolvedAt"] = "2026-04-01T09:02:31Z"
            item["updatedAt"] = "2026-04-01T09:02:31Z"
        storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, snapshot)
        return {
            "requestId": request_id,
            "itemId": "ask-input-1",
            "threadId": thread_id,
            "turnId": "ask-turn-1",
            "status": "answer_submitted",
            "answers": answers,
            "submittedAt": "2026-04-01T09:02:30Z",
        }

    client.app.state.thread_runtime_service_v3.resolve_user_input = _fake_resolve_user_input

    resolve_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/requests/ask-req-1/resolve",
        params={"node_id": node_id},
        json={"answers": [{"questionId": "q1", "value": "Option A", "label": "Option A"}]},
    )
    assert resolve_response.status_code == 200
    resolve_payload = resolve_response.json()
    assert resolve_payload["ok"] is True
    assert resolve_payload["data"]["status"] == "answer_submitted"

    snapshot_response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}",
        params={"node_id": node_id},
    )
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    snapshot_v3 = snapshot_payload["data"]["snapshot"]
    assert snapshot_v3["processingState"] == "idle"
    assert snapshot_v3["uiSignals"]["activeUserInputRequests"][0]["status"] == "answered"


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

    client.app.state.execution_audit_workflow_service.start_execution_followup = (
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


def test_v3_plan_actions_on_ask_thread_reject_policy(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)

    response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions",
        params={"node_id": node_id},
        json={
            "action": "implement_plan",
            "planItemId": "plan-1",
            "revision": 1,
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"


def test_v3_ask_reset_by_id_clears_thread_snapshot(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)
    _seed_ask_user_input_pending(client, project_id, node_id, thread_id=thread_id)

    response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/reset",
        params={"node_id": node_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["threadId"] is None
    assert int(payload["data"]["snapshotVersion"]) >= 1

    snapshot = client.app.state.storage.thread_snapshot_store_v3.read_snapshot(
        project_id,
        node_id,
        "ask_planning",
    )
    assert snapshot["threadId"] is None
    assert snapshot["items"] == []
    assert snapshot["uiSignals"]["activeUserInputRequests"] == []


def test_v3_reset_policy_rejects_execution_and_audit_threads(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    execution_thread_id = _seed_execution_thread(client, project_id, node_id)
    audit_thread_id = _seed_audit_thread(client, project_id, node_id)

    execution_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{execution_thread_id}/reset",
        params={"node_id": node_id},
    )
    assert execution_response.status_code == 400
    execution_payload = execution_response.json()
    assert execution_payload["ok"] is False
    assert execution_payload["error"]["code"] == "invalid_request"

    audit_response = client.post(
        f"/v3/projects/{project_id}/threads/by-id/{audit_thread_id}/reset",
        params={"node_id": node_id},
    )
    assert audit_response.status_code == 400
    audit_payload = audit_response.json()
    assert audit_payload["ok"] is False
    assert audit_payload["error"]["code"] == "invalid_request"


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
        stream_open_chunk = await _read_stream_chunk(response)
        assert not any(line.startswith("id: ") for line in stream_open_chunk.splitlines())
        stream_open_payload = _parse_sse_chunk(stream_open_chunk)
        assert stream_open_payload["type"] == event_types.STREAM_OPEN
        assert int(stream_open_payload["snapshotVersion"]) >= 1

        snapshot_chunk = await _read_stream_chunk(response)
        assert snapshot_chunk.startswith("id: ")
        first_payload = _parse_sse_chunk(snapshot_chunk)
        assert first_payload["type"] == event_types.THREAD_SNAPSHOT_V3
        assert first_payload["event_id"] == first_payload["eventId"]
        snapshot_id_line = next(line for line in snapshot_chunk.splitlines() if line.startswith("id: "))
        assert snapshot_id_line == f"id: {first_payload['event_id']}"
        assert first_payload["payload"]["snapshot"]["threadId"] == thread_id
        first_snapshot_version = int(first_payload.get("snapshotVersion") or 0)

        envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=max(1, first_snapshot_version + 1),
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="200",
            thread_id=thread_id,
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
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            envelope,
            thread_role="execution",
        )

        incremental_payload = await _read_sse_payload(response)
        assert incremental_payload["type"] == event_types.CONVERSATION_ITEM_UPSERT_V3
        assert incremental_payload["event_id"] == "200"
        assert incremental_payload["payload"]["item"]["id"] == "msg-2"
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_thread_events_stream_closes_lagged_subscriber_without_silent_continuation(
    client: TestClient, workspace_root
) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    lagged_broker = ChatEventBroker(subscriber_queue_max=1)
    client.app.state.conversation_event_broker_v3 = lagged_broker

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.thread_events_by_id_v3(
        request,
        project_id,
        thread_id,
        node_id=node_id,
        after_snapshot_version=1,
    )
    try:
        stream_open_payload = await _read_sse_payload(response)
        assert stream_open_payload["type"] == event_types.STREAM_OPEN
        snapshot_payload = await _read_sse_payload(response)
        assert snapshot_payload["type"] == event_types.THREAD_SNAPSHOT_V3
        first_snapshot_version = int(snapshot_payload.get("snapshotVersion") or 0)

        for idx in range(4):
            event_id = str(900 + idx)
            lagged_broker.publish(
                project_id,
                node_id,
                build_thread_envelope(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="execution",
                    snapshot_version=max(1, first_snapshot_version + idx + 1),
                    event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
                    event_id=event_id,
                    thread_id=thread_id,
                    payload={
                        "item": {
                            "id": f"msg-{event_id}",
                            "kind": "message",
                            "threadId": thread_id,
                            "turnId": f"turn-{event_id}",
                            "sequence": first_snapshot_version + idx + 1,
                            "createdAt": "2026-04-01T10:06:00Z",
                            "updatedAt": "2026-04-01T10:06:00Z",
                            "status": "completed",
                            "source": "upstream",
                            "tone": "neutral",
                            "metadata": {},
                            "role": "assistant",
                            "text": f"Lagged event {event_id}",
                            "format": "markdown",
                        }
                    },
                ),
                thread_role="execution",
            )
        await asyncio.sleep(0)
        await _assert_stream_closed(response, timeout_sec=1.0)
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_execution_stream_drops_mismatched_thread_id_events(client: TestClient, workspace_root) -> None:
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
        _ = await _read_stream_chunk(response)  # stream_open
        snapshot_chunk = await _read_stream_chunk(response)
        first_payload = _parse_sse_chunk(snapshot_chunk)
        first_snapshot_version = int(first_payload.get("snapshotVersion") or 0)
        next_snapshot_version = max(1, first_snapshot_version + 1)

        mismatched_envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=next_snapshot_version,
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="400",
            thread_id="exec-thread-v3-2",
            payload={
                "item": {
                    "id": "msg-mismatch",
                    "kind": "message",
                    "threadId": "exec-thread-v3-2",
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:01:00Z",
                    "updatedAt": "2026-04-01T10:01:00Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Wrong thread",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            mismatched_envelope,
            thread_role="execution",
        )

        valid_envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=next_snapshot_version,
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="401",
            thread_id=thread_id,
            payload={
                "item": {
                    "id": "msg-valid",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:01:01Z",
                    "updatedAt": "2026-04-01T10:01:01Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Correct thread",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            valid_envelope,
            thread_role="execution",
        )

        payload = await _read_sse_payload(response)
        assert payload["event_id"] == "401"
        assert payload["payload"]["item"]["threadId"] == thread_id
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_execution_stream_drops_missing_thread_id_events_and_stays_healthy(client: TestClient, workspace_root) -> None:
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
        _ = await _read_stream_chunk(response)  # stream_open
        snapshot_chunk = await _read_stream_chunk(response)
        first_payload = _parse_sse_chunk(snapshot_chunk)
        first_snapshot_version = int(first_payload.get("snapshotVersion") or 0)
        next_snapshot_version = max(1, first_snapshot_version + 1)

        missing_thread_envelope = {
            "schema_version": 1,
            "event_id": "500",
            "event_type": event_types.CONVERSATION_ITEM_UPSERT_V3,
            "turn_id": None,
            "snapshot_version": next_snapshot_version,
            "occurred_at_ms": int(first_payload.get("occurred_at_ms") or 0) + 1,
            "payload": {
                "item": {
                    "id": "msg-missing-thread",
                    "kind": "message",
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:01:00Z",
                    "updatedAt": "2026-04-01T10:01:00Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Missing thread id",
                    "format": "markdown",
                }
            },
            "eventId": "500",
            "channel": "thread",
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "occurredAt": "2026-04-01T10:01:00Z",
            "snapshotVersion": next_snapshot_version,
            "type": event_types.CONVERSATION_ITEM_UPSERT_V3,
        }
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            missing_thread_envelope,
            thread_role="execution",
        )

        valid_envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=next_snapshot_version,
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="501",
            thread_id=thread_id,
            payload={
                "item": {
                    "id": "msg-valid-after-drop",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:01:01Z",
                    "updatedAt": "2026-04-01T10:01:01Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Still healthy",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            valid_envelope,
            thread_role="execution",
        )

        payload = await _read_sse_payload(response)
        assert payload["event_id"] == "501"
        assert payload["payload"]["item"]["id"] == "msg-valid-after-drop"
    finally:
        await _close_stream(response, request)


@pytest.mark.anyio
async def test_v3_ask_stream_emits_snapshot_and_incremental_events(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    _stub_ask_session_reads(client)
    thread_id = _seed_ask_thread(client, project_id, node_id)

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.thread_events_by_id_v3(
        request,
        project_id,
        thread_id,
        node_id=node_id,
        after_snapshot_version=1,
    )

    try:
        stream_open_chunk = await _read_stream_chunk(response)
        assert not any(line.startswith("id: ") for line in stream_open_chunk.splitlines())
        stream_open_payload = _parse_sse_chunk(stream_open_chunk)
        assert stream_open_payload["type"] == event_types.STREAM_OPEN
        assert stream_open_payload["payload"]["threadRole"] == "ask_planning"

        snapshot_chunk = await _read_stream_chunk(response)
        assert snapshot_chunk.startswith("id: ")
        first_payload = _parse_sse_chunk(snapshot_chunk)
        assert first_payload["type"] == event_types.THREAD_SNAPSHOT_V3
        snapshot_id_line = next(line for line in snapshot_chunk.splitlines() if line.startswith("id: "))
        assert snapshot_id_line == f"id: {first_payload['event_id']}"
        assert first_payload["payload"]["snapshot"]["threadId"] == thread_id
        assert first_payload["payload"]["snapshot"]["threadRole"] == "ask_planning"
        assert "lane" not in first_payload["payload"]["snapshot"]
        first_snapshot_version = int(first_payload.get("snapshotVersion") or 0)

        envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="ask_planning",
            snapshot_version=max(1, first_snapshot_version + 1),
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="300",
            thread_id=thread_id,
            payload={
                "item": {
                    "id": "ask-msg-2",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "ask-turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T09:01:00Z",
                    "updatedAt": "2026-04-01T09:01:00Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Incremental ask note",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            envelope,
            thread_role="ask_planning",
        )

        incremental_payload = await _read_sse_payload(response)
        assert incremental_payload["type"] == event_types.CONVERSATION_ITEM_UPSERT_V3
        assert incremental_payload["event_id"] == "300"
        assert incremental_payload["payload"]["item"]["id"] == "ask-msg-2"
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
        stream_open_payload = await _read_sse_payload(response)
        assert stream_open_payload["type"] == event_types.STREAM_OPEN
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


@pytest.mark.anyio
async def test_v3_execution_stream_replays_cursor_range_and_dedupes_live_boundary(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    client.app.state.thread_query_service_v3.get_thread_snapshot(
        project_id,
        node_id,
        "execution",
        publish_repairs=False,
        ensure_binding=False,
    )

    replay_buffer = client.app.state.thread_replay_buffer_service_v3
    replay_envelope = build_thread_envelope(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        snapshot_version=2,
        event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
        event_id="201",
        thread_id=thread_id,
        payload={
            "item": {
                "id": "msg-replay-201",
                "kind": "message",
                "threadId": thread_id,
                "turnId": "turn-2",
                "sequence": 2,
                "createdAt": "2026-04-01T10:02:00Z",
                "updatedAt": "2026-04-01T10:02:00Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "role": "assistant",
                "text": "Replay event",
                "format": "markdown",
            }
        },
    )
    replay_buffer.append_business_event(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        thread_id=thread_id,
        envelope=replay_envelope,
    )

    request = _StreamingTestRequest(client.app)
    response = await workflow_v3_route_module.thread_events_by_id_v3(
        request,
        project_id,
        thread_id,
        node_id=node_id,
        last_event_id="200",
    )

    try:
        stream_open_payload = await _read_sse_payload(response)
        assert stream_open_payload["type"] == event_types.STREAM_OPEN

        replay_payload = await _read_sse_payload(response)
        assert replay_payload["event_id"] == "201"
        assert replay_payload["type"] == event_types.CONVERSATION_ITEM_UPSERT_V3

        duplicate_boundary = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=2,
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="201",
            thread_id=thread_id,
            payload={
                "item": {
                    "id": "msg-replay-201-dup",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "turn-2",
                    "sequence": 2,
                    "createdAt": "2026-04-01T10:02:01Z",
                    "updatedAt": "2026-04-01T10:02:01Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Duplicate boundary event",
                    "format": "markdown",
                }
            },
        )
        live_next = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            snapshot_version=3,
            event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
            event_id="202",
            thread_id=thread_id,
            payload={
                "item": {
                    "id": "msg-live-202",
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": "turn-3",
                    "sequence": 3,
                    "createdAt": "2026-04-01T10:03:00Z",
                    "updatedAt": "2026-04-01T10:03:00Z",
                    "status": "completed",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "Live event",
                    "format": "markdown",
                }
            },
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            duplicate_boundary,
            thread_role="execution",
        )
        client.app.state.conversation_event_broker_v3.publish(
            project_id,
            node_id,
            live_next,
            thread_role="execution",
        )

        next_payload = await _read_sse_payload(response)
        assert next_payload["event_id"] == "202"
        assert next_payload["payload"]["item"]["id"] == "msg-live-202"
    finally:
        await _close_stream(response, request)


def test_v3_execution_stream_replay_miss_returns_409(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    client.app.state.thread_query_service_v3.get_thread_snapshot(
        project_id,
        node_id,
        "execution",
        publish_repairs=False,
        ensure_binding=False,
    )

    replay_buffer = client.app.state.thread_replay_buffer_service_v3
    replay_buffer._max_events = 1  # type: ignore[attr-defined]

    for event_id, version in [("100", 2), ("101", 3)]:
        replay_buffer.append_business_event(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            thread_id=thread_id,
            envelope=build_thread_envelope(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                snapshot_version=version,
                event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
                event_id=event_id,
                thread_id=thread_id,
                payload={
                    "item": {
                        "id": f"msg-{event_id}",
                        "kind": "message",
                        "threadId": thread_id,
                        "turnId": f"turn-{event_id}",
                        "sequence": version,
                        "createdAt": "2026-04-01T10:04:00Z",
                        "updatedAt": "2026-04-01T10:04:00Z",
                        "status": "completed",
                        "source": "upstream",
                        "tone": "neutral",
                        "metadata": {},
                        "role": "assistant",
                        "text": f"Event {event_id}",
                        "format": "markdown",
                    }
                },
            ),
        )

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/events",
        params={"node_id": node_id, "last_event_id": "99"},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "conversation_stream_mismatch"
    assert "replay_miss" in str(payload["error"]["message"])


def test_v3_execution_stream_cursor_header_precedence_over_query(client: TestClient, workspace_root) -> None:
    project_id, node_id = _setup_project(client, workspace_root)
    thread_id = _seed_execution_thread(client, project_id, node_id)
    client.app.state.thread_query_service_v3.get_thread_snapshot(
        project_id,
        node_id,
        "execution",
        publish_repairs=False,
        ensure_binding=False,
    )

    replay_buffer = client.app.state.thread_replay_buffer_service_v3
    replay_buffer._max_events = 1  # type: ignore[attr-defined]

    for event_id, version in [("100", 2), ("101", 3)]:
        replay_buffer.append_business_event(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            thread_id=thread_id,
            envelope=build_thread_envelope(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                snapshot_version=version,
                event_type=event_types.CONVERSATION_ITEM_UPSERT_V3,
                event_id=event_id,
                thread_id=thread_id,
                payload={
                    "item": {
                        "id": f"msg-{event_id}",
                        "kind": "message",
                        "threadId": thread_id,
                        "turnId": f"turn-{event_id}",
                        "sequence": version,
                        "createdAt": "2026-04-01T10:05:00Z",
                        "updatedAt": "2026-04-01T10:05:00Z",
                        "status": "completed",
                        "source": "upstream",
                        "tone": "neutral",
                        "metadata": {},
                        "role": "assistant",
                        "text": f"Event {event_id}",
                        "format": "markdown",
                    }
                },
            ),
        )

    response = client.get(
        f"/v3/projects/{project_id}/threads/by-id/{thread_id}/events",
        params={"node_id": node_id, "last_event_id": "101"},
        headers={"Last-Event-ID": "99"},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "conversation_stream_mismatch"
    assert "replay_miss" in str(payload["error"]["message"])
