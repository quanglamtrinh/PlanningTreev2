from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from backend.routes import chat_v2 as chat_v2_route_module


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


async def _close_stream(response: Any, request: _StreamingTestRequest) -> None:
    request.disconnect()
    body_iterator = response.body_iterator
    if hasattr(body_iterator, "aclose"):
        await body_iterator.aclose()


def _parse_sse_chunk(chunk: str) -> dict[str, Any]:
    data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    return json.loads(data_line[len("data: ") :])


def _setup_project(client: TestClient, workspace_root) -> tuple[str, str]:
    resp = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert resp.status_code == 200
    snap = resp.json()
    return snap["project"]["id"], snap["tree_state"]["root_node_id"]


def _set_v2_codex_client(client: TestClient, codex_client: object) -> None:
    client.app.state.codex_client = codex_client
    client.app.state.chat_service._codex_client = codex_client
    client.app.state.thread_lineage_service._codex_client = codex_client
    client.app.state.thread_query_service_v2._codex_client = codex_client
    client.app.state.thread_runtime_service_v2._codex_client = codex_client


def _wait_for_snapshot(
    client: TestClient,
    project_id: str,
    node_id: str,
    thread_role: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout_sec: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        snapshot = payload["data"]["snapshot"]
        last_snapshot = snapshot
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for snapshot condition. Last snapshot: {last_snapshot!r}")


class FakeConversationV2CodexClient:
    def __init__(self, turn_id_resolver: Callable[[], str | None]) -> None:
        self._turn_id_resolver = turn_id_resolver
        self.started_threads: list[str] = []
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"audit-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"ask-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        on_raw_event = kwargs.get("on_raw_event")
        thread_id = str(kwargs.get("thread_id") or "thread-1")
        turn_id = str(self._turn_id_resolver() or "turn-1")
        if callable(on_raw_event):
            on_raw_event(
                {
                    "method": "item/started",
                    "received_at": "2026-03-28T10:00:01Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "msg-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
                }
            )
            on_raw_event(
                {
                    "method": "item/agentMessage/delta",
                    "received_at": "2026-03-28T10:00:02Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "msg-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"delta": "Hello from V2"},
                }
            )
            on_raw_event(
                {
                    "method": "item/tool/call",
                    "received_at": "2026-03-28T10:00:03Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": None,
                    "request_id": None,
                    "call_id": "call-1",
                    "params": {
                        "toolName": "apply_patch",
                        "tool_name": "apply_patch",
                        "arguments": {"path": "preview.txt"},
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/started",
                    "received_at": "2026-03-28T10:00:04Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "item": {
                            "type": "fileChange",
                            "id": "file-1",
                            "callId": "call-1",
                            "toolName": "apply_patch",
                        }
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/fileChange/outputDelta",
                    "received_at": "2026-03-28T10:00:05Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "delta": "preview",
                        "files": [{"path": "preview.txt", "changeType": "created", "summary": "preview"}],
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/completed",
                    "received_at": "2026-03-28T10:00:06Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "item": {
                            "type": "fileChange",
                            "id": "file-1",
                            "changes": [{"path": "final.txt", "changeType": "updated", "summary": "final"}],
                        }
                    },
                }
            )
            on_raw_event(
                {
                    "method": "turn/completed",
                    "received_at": "2026-03-28T10:00:07Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": None,
                    "request_id": None,
                    "call_id": None,
                    "params": {"turn": {"id": turn_id, "status": "completed"}},
                }
            )
        return {"stdout": "Hello from V2", "thread_id": thread_id, "turn_id": turn_id, "turn_status": "completed"}

    def get_runtime_request(self, request_id: str) -> None:
        del request_id
        return None

    def resolve_runtime_request_user_input(self, request_id: str, *, answers: dict[str, Any]) -> None:
        del request_id, answers
        return None


class FakeUserInputV2CodexClient(FakeConversationV2CodexClient):
    def __init__(self, turn_id_resolver: Callable[[], str | None]) -> None:
        super().__init__(turn_id_resolver)
        self._requests: dict[str, Any] = {}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        on_raw_event = kwargs.get("on_raw_event")
        thread_id = str(kwargs.get("thread_id") or "thread-1")
        turn_id = str(self._turn_id_resolver() or "turn-1")
        if callable(on_raw_event):
            on_raw_event(
                {
                    "method": "item/tool/requestUserInput",
                    "received_at": "2026-03-28T10:00:01Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "input-1",
                    "request_id": "req-1",
                    "call_id": None,
                    "params": {
                        "questions": [
                            {
                                "id": "q1",
                                "header": "Choice",
                                "prompt": "Pick one",
                                "inputType": "single_select",
                                "options": [{"label": "Option A", "description": "A"}],
                            }
                        ]
                    },
                }
            )
            self._requests["req-1"] = SimpleNamespace(
                request_id="req-1",
                item_id="input-1",
                thread_id=thread_id,
                turn_id=turn_id,
                status="pending",
            )
            on_raw_event(
                {
                    "method": "turn/completed",
                    "received_at": "2026-03-28T10:00:02Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": None,
                    "request_id": None,
                    "call_id": None,
                    "params": {"turn": {"id": turn_id, "status": "waiting_user_input"}},
                }
            )
        return {
            "stdout": "",
            "thread_id": thread_id,
            "turn_id": turn_id,
            "turn_status": "waiting_user_input",
        }

    def get_runtime_request(self, request_id: str) -> Any:
        return self._requests.get(str(request_id))

    def resolve_runtime_request_user_input(self, request_id: str, *, answers: dict[str, Any]) -> Any:
        record = self._requests.get(str(request_id))
        if record is None:
            return None
        record.status = "answered"
        record.answers = dict(answers)
        return record


def test_v2_get_thread_snapshot_returns_wrapped_envelope(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    snapshot = payload["data"]["snapshot"]
    assert snapshot["threadRole"] == "ask_planning"
    assert snapshot["threadId"].startswith("ask-thread-")


@pytest.mark.anyio
async def test_v2_thread_events_emits_first_snapshot_frame(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    request = _StreamingTestRequest(client.app)
    response = await chat_v2_route_module.thread_events_v2(request, project_id, root_id, "ask_planning", None)

    try:
        assert response.media_type == "text/event-stream"
        first_chunk = await _read_stream_chunk(response)
    finally:
        await _close_stream(response, request)

    payload = _parse_sse_chunk(first_chunk)
    assert payload["type"] == "thread.snapshot"
    assert payload["payload"]["snapshot"]["threadRole"] == "ask_planning"


def test_v2_start_turn_persists_items_and_authoritative_file_list(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Hello V2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    created = payload["data"]["createdItems"]
    assert len(created) == 1
    assert created[0]["role"] == "user"

    snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle"
        and any(item["id"] == "msg-1" for item in snap["items"])
        and any(item["id"] == "file-1" and item["status"] == "completed" for item in snap["items"]),
    )

    assistant = next(item for item in snapshot["items"] if item["id"] == "msg-1")
    file_tool = next(item for item in snapshot["items"] if item["id"] == "file-1")
    assert assistant["text"] == "Hello from V2"
    assert file_tool["outputFiles"] == [
        {"path": "final.txt", "changeType": "updated", "summary": "final"}
    ]


def test_v2_invalid_after_snapshot_version_returns_wrapped_error(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    snapshot_resp = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning")
    snapshot_version = snapshot_resp.json()["data"]["snapshot"]["snapshotVersion"]

    response = client.get(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/events",
        params={"after_snapshot_version": snapshot_version + 10},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "conversation_stream_mismatch"


def test_v2_resolve_user_input_updates_item_and_ledger(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeUserInputV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    start_response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Need input"},
    )
    assert start_response.status_code == 200

    waiting_snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "waiting_user_input" and len(snap["pendingRequests"]) == 1,
    )
    pending = waiting_snapshot["pendingRequests"][0]
    assert pending["requestId"] == "req-1"

    resolve_response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/requests/req-1/resolve",
        json={"answers": [{"questionId": "q1", "value": "option_a", "label": "Option A"}]},
    )

    assert resolve_response.status_code == 200
    resolve_payload = resolve_response.json()
    assert resolve_payload["ok"] is True
    assert resolve_payload["data"]["status"] == "answer_submitted"

    resolved_snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle"
        and snap["pendingRequests"]
        and snap["pendingRequests"][0]["status"] == "answered",
    )
    user_input = next(item for item in resolved_snapshot["items"] if item["id"] == "input-1")
    assert user_input["status"] == "answered"
    assert user_input["answers"] == [
        {"questionId": "q1", "value": "option_a", "label": "Option A"}
    ]
