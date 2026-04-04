from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from backend.conversation.domain import events as event_types
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


async def _read_sse_payload(response: Any, *, timeout_sec: float = 1.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        chunk = await _read_stream_chunk(response, timeout_sec=timeout_sec)
        if chunk.lstrip().startswith(":"):
            continue
        return _parse_sse_chunk(chunk)
    raise AssertionError("Timed out waiting for SSE payload.")


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


def _seed_metadata_repair_state(
    client: TestClient,
    project_id: str,
    node_id: str,
    thread_role: str,
    *,
    minimum_snapshot_version: int,
) -> None:
    storage = client.app.state.storage
    session = storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)
    session["forked_from_thread_id"] = "repair-source-thread"
    session["forked_from_node_id"] = "repair-source-node"
    session["forked_from_role"] = "audit"
    session["fork_reason"] = "metadata_repair"
    session["lineage_root_thread_id"] = "repair-root-thread"
    storage.chat_state_store.write_session(project_id, node_id, session, thread_role=thread_role)

    stale_snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, thread_role)
    stale_snapshot["lineage"] = {
        "forkedFromThreadId": "stale-thread",
        "forkedFromNodeId": "stale-node",
        "forkedFromRole": "execution",
        "forkReason": "stale",
        "lineageRootThreadId": "stale-root",
    }
    stale_snapshot["snapshotVersion"] = max(
        int(stale_snapshot.get("snapshotVersion") or 0),
        int(minimum_snapshot_version),
    )
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, thread_role, stale_snapshot)


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
                    "method": "turn/completed",
                    "received_at": "2026-03-28T10:00:03Z",
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


class FakeThreadReadBackfillCodexClient:
    def start_thread(self, **_: object) -> dict[str, str]:
        return {"thread_id": "thread-backfill-1"}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": f"forked-from-{source_thread_id}"}

    def get_runtime_request(self, request_id: str) -> None:
        del request_id
        return None

    def read_thread(self, thread_id: str, *, include_turns: bool = False, timeout_sec: int = 30) -> dict[str, Any]:
        del include_turns, timeout_sec
        return {
            "thread": {
                "id": thread_id,
                "createdAt": 1774773247,
                "updatedAt": 1774773577,
                "turns": [
                    {
                        "id": "019d38b6-8f4b-76a0-a4e1-c330e61c6ef8",
                        "status": "completed",
                        "items": [
                            {
                                "type": "agentMessage",
                                "id": "old-assistant",
                                "text": "older inherited answer",
                                "phase": "final_answer",
                            }
                        ],
                    },
                    {
                        "id": "019d38bc-1854-7df2-843e-88ef9c7d3077",
                        "status": "completed",
                        "items": [
                            {
                                "type": "userMessage",
                                "id": "exec-user",
                                "content": [{"type": "text", "text": "internal execution prompt"}],
                            },
                            {
                                "type": "agentMessage",
                                "id": "exec-commentary",
                                "text": "I am checking the repo layout.",
                                "phase": "commentary",
                            },
                            {
                                "type": "agentMessage",
                                "id": "exec-final",
                                "text": "Implemented the browser round interface.",
                                "phase": "final_answer",
                            },
                        ],
                    },
                ],
            }
        }


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


class FileChangeAskV2CodexClient(FakeConversationV2CodexClient):
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
                    "params": {"delta": "Attempting file change"},
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
        return {"stdout": "Attempting file change", "thread_id": thread_id, "turn_id": turn_id, "turn_status": "completed"}


class CapturingAskSandboxV2CodexClient(FakeConversationV2CodexClient):
    def __init__(self, turn_id_resolver: Callable[[], str | None]) -> None:
        super().__init__(turn_id_resolver)
        self.run_kwargs: list[dict[str, Any]] = []

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        self.run_kwargs.append(dict(kwargs))
        return super().run_turn_streaming(prompt, **kwargs)


class FakeIncompleteItemsV2CodexClient(FakeConversationV2CodexClient):
    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        on_raw_event = kwargs.get("on_raw_event")
        thread_id = str(kwargs.get("thread_id") or "thread-1")
        turn_id = str(self._turn_id_resolver() or "turn-1")
        if callable(on_raw_event):
            on_raw_event(
                {
                    "method": "item/reasoning/summaryDelta",
                    "received_at": "2026-03-28T10:00:01Z",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "item_id": "reason-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"delta": "thinking"},
                }
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
                    "params": {"turn": {"id": turn_id, "status": "completed"}},
                }
            )
        return {
            "stdout": "",
            "thread_id": thread_id,
            "turn_id": turn_id,
            "turn_status": "completed",
        }


class FailingConversationV2CodexClient(FakeConversationV2CodexClient):
    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        on_raw_event = kwargs.get("on_raw_event")
        thread_id = str(kwargs.get("thread_id") or "thread-1")
        turn_id = str(self._turn_id_resolver() or "turn-1")
        if not callable(on_raw_event):
            return {
                "stdout": "",
                "thread_id": thread_id,
                "turn_id": turn_id,
                "turn_status": "completed",
            }
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
                    "params": {"delta": "partial assistant output"},
                }
            )
        raise RuntimeError("Simulated turn failure")


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


@pytest.mark.anyio
async def test_v2_get_thread_snapshot_repairs_metadata_and_publishes_snapshot_event(
    client: TestClient, workspace_root
) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    initial_response = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning")
    assert initial_response.status_code == 200
    initial_snapshot = initial_response.json()["data"]["snapshot"]

    _seed_metadata_repair_state(
        client,
        project_id,
        root_id,
        "ask_planning",
        minimum_snapshot_version=int(initial_snapshot["snapshotVersion"]),
    )

    queue = client.app.state.conversation_event_broker_v2.subscribe(project_id, root_id, thread_role="ask_planning")
    try:
        repaired_response = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning")
        assert repaired_response.status_code == 200
        repaired_snapshot = repaired_response.json()["data"]["snapshot"]
        envelope = await asyncio.wait_for(queue.get(), timeout=1.0)
    finally:
        client.app.state.conversation_event_broker_v2.unsubscribe(
            project_id,
            root_id,
            queue,
            thread_role="ask_planning",
        )

    assert envelope["type"] == event_types.THREAD_SNAPSHOT
    assert repaired_snapshot["lineage"] == {
        "forkedFromThreadId": "repair-source-thread",
        "forkedFromNodeId": "repair-source-node",
        "forkedFromRole": "audit",
        "forkReason": "metadata_repair",
        "lineageRootThreadId": "repair-root-thread",
    }
    assert envelope["payload"]["snapshot"]["lineage"] == repaired_snapshot["lineage"]


@pytest.mark.anyio
async def test_v2_thread_events_stream_open_repairs_metadata_and_publishes_to_existing_subscribers(
    client: TestClient, workspace_root
) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    initial_response = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning")
    assert initial_response.status_code == 200
    initial_snapshot = initial_response.json()["data"]["snapshot"]

    request_a = _StreamingTestRequest(client.app)
    response_a = await chat_v2_route_module.thread_events_v2(
        request_a,
        project_id,
        root_id,
        "ask_planning",
        initial_snapshot["snapshotVersion"],
    )

    request_b: _StreamingTestRequest | None = None
    response_b = None
    try:
        first_a = await _read_sse_payload(response_a)
        assert first_a["type"] == event_types.THREAD_SNAPSHOT
        assert first_a["payload"]["snapshot"]["lineage"] == initial_snapshot["lineage"]

        _seed_metadata_repair_state(
            client,
            project_id,
            root_id,
            "ask_planning",
            minimum_snapshot_version=int(initial_snapshot["snapshotVersion"]),
        )

        request_b = _StreamingTestRequest(client.app)
        response_b = await chat_v2_route_module.thread_events_v2(
            request_b,
            project_id,
            root_id,
            "ask_planning",
            initial_snapshot["snapshotVersion"],
        )

        repaired_for_a = await _read_sse_payload(response_a)
        first_b = await _read_sse_payload(response_b)

        assert repaired_for_a["type"] == event_types.THREAD_SNAPSHOT
        assert first_b["type"] == event_types.THREAD_SNAPSHOT
        assert repaired_for_a["payload"]["snapshot"]["lineage"] == {
            "forkedFromThreadId": "repair-source-thread",
            "forkedFromNodeId": "repair-source-node",
            "forkedFromRole": "audit",
            "forkReason": "metadata_repair",
            "lineageRootThreadId": "repair-root-thread",
        }
        assert first_b["payload"]["snapshot"]["lineage"] == repaired_for_a["payload"]["snapshot"]["lineage"]

        with pytest.raises(asyncio.TimeoutError):
            await _read_stream_chunk(response_b, timeout_sec=0.1)
    finally:
        if response_b is not None and request_b is not None:
            await _close_stream(response_b, request_b)
        await _close_stream(response_a, request_a)


def test_v2_start_turn_persists_items(client: TestClient, workspace_root) -> None:
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
        and any(item["id"] == "msg-1" for item in snap["items"]),
    )

    assistant = next(item for item in snapshot["items"] if item["id"] == "msg-1")
    assert assistant["text"] == "Hello from V2"


def test_v2_ask_turn_runs_with_read_only_sandbox(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = CapturingAskSandboxV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Hello read-only ask"},
    )
    assert response.status_code == 200
    _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle",
    )

    assert codex.run_kwargs
    run_kwargs = codex.run_kwargs[-1]
    assert run_kwargs.get("sandbox_profile") == "read_only"
    assert run_kwargs.get("writable_roots") is None


def test_v2_ask_turn_fails_when_file_change_item_is_emitted(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FileChangeAskV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Try changing files"},
    )
    assert response.status_code == 200

    snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle"
        and any(item["kind"] == "error" for item in snap["items"]),
    )
    error_item = next(item for item in snapshot["items"] if item["kind"] == "error")
    assert "Ask lane is read-only" in error_item["message"]


def test_v2_start_turn_rejects_execution_thread_messages(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/execution/turns",
        json={"text": "Hello execution"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"
    assert "Use /v3 by-id APIs." in payload["error"]["message"]


def test_v2_terminal_success_finalizes_open_items_when_upstream_omits_item_completed(
    client: TestClient, workspace_root
) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeIncompleteItemsV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Finish open items"},
    )

    assert response.status_code == 200

    snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle" and any(item["id"] == "reason-1" for item in snap["items"]),
    )

    reasoning = next(item for item in snapshot["items"] if item["id"] == "reason-1")
    assert reasoning["status"] == "completed"


def test_v2_failed_turn_error_item_sorts_after_existing_items(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FailingConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Fail this turn"},
    )

    assert response.status_code == 200

    snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle"
        and any(item["kind"] == "error" for item in snap["items"])
        and any(item["id"] == "msg-1" for item in snap["items"]),
    )

    assistant = next(item for item in snapshot["items"] if item["id"] == "msg-1")
    error_item = next(item for item in snapshot["items"] if item["kind"] == "error")

    assert assistant["status"] == "failed"
    assert error_item["id"].startswith("error:")
    assert error_item["sequence"] == max(int(item["sequence"]) for item in snapshot["items"])
    assert snapshot["items"][-1]["id"] == error_item["id"]


@pytest.mark.anyio
async def test_v2_reset_route_streams_reset_then_fresh_snapshot(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    codex = FakeConversationV2CodexClient(
        lambda: client.app.state.storage.chat_state_store.read_session(
            project_id,
            root_id,
            thread_role="ask_planning",
        )["active_turn_id"]
    )
    _set_v2_codex_client(client, codex)

    start_response = client.post(
        f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/turns",
        json={"text": "Reset me"},
    )
    assert start_response.status_code == 200

    settled_snapshot = _wait_for_snapshot(
        client,
        project_id,
        root_id,
        "ask_planning",
        lambda snap: snap["processingState"] == "idle" and len(snap["items"]) >= 2,
    )

    request = _StreamingTestRequest(client.app)
    response = await chat_v2_route_module.thread_events_v2(
        request,
        project_id,
        root_id,
        "ask_planning",
        settled_snapshot["snapshotVersion"],
    )

    try:
        first_payload = await _read_sse_payload(response)
        reset_response = client.post(
            f"/v2/projects/{project_id}/nodes/{root_id}/threads/ask_planning/reset",
        )
        assert reset_response.status_code == 200

        second_payload = await _read_sse_payload(response)
        third_payload = await _read_sse_payload(response)
    finally:
        await _close_stream(response, request)

    assert first_payload["type"] == event_types.THREAD_SNAPSHOT
    assert second_payload["type"] == event_types.THREAD_RESET
    assert third_payload["type"] == event_types.THREAD_SNAPSHOT
    assert third_payload["payload"]["snapshot"]["items"] == []
    assert third_payload["payload"]["snapshot"]["pendingRequests"] == []
    assert third_payload["payload"]["snapshot"]["processingState"] == "idle"


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


def test_v2_execution_snapshot_is_rejected(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)

    response = client.get(f"/v2/projects/{project_id}/nodes/{root_id}/threads/execution")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_request"
    assert "Use /v3 by-id APIs." in payload["error"]["message"]


@pytest.mark.anyio
async def test_v2_workflow_stream_emits_wrapped_v2_workflow_envelopes(client: TestClient, workspace_root) -> None:
    project_id, root_id = _setup_project(client, workspace_root)
    request = _StreamingTestRequest(client.app)
    response = await chat_v2_route_module.workflow_events_v2(request, project_id)

    try:
        client.app.state.workflow_event_publisher_v2.publish_workflow_updated(
            project_id=project_id,
            node_id=root_id,
            execution_state="completed",
            review_state="running",
        )
        client.app.state.workflow_event_publisher_v2.publish_detail_invalidate(
            project_id=project_id,
            node_id=root_id,
            reason="execution_completed",
        )

        workflow_payload = await _read_sse_payload(response)
        invalidate_payload = await _read_sse_payload(response)
    finally:
        await _close_stream(response, request)

    assert workflow_payload["channel"] == event_types.WORKFLOW_CHANNEL
    assert workflow_payload["type"] == event_types.NODE_WORKFLOW_UPDATED
    assert workflow_payload["payload"] == {
        "projectId": project_id,
        "nodeId": root_id,
        "executionState": "completed",
        "reviewState": "running",
        "activeExecutionRunId": None,
        "activeReviewCycleId": None,
        "workflowPhase": None,
    }
    assert invalidate_payload["channel"] == event_types.WORKFLOW_CHANNEL
    assert invalidate_payload["type"] == event_types.NODE_DETAIL_INVALIDATE
    assert invalidate_payload["payload"] == {
        "projectId": project_id,
        "nodeId": root_id,
        "reason": "execution_completed",
    }
