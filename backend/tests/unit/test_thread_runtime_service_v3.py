from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import backend.conversation.services.thread_runtime_service_v3 as thread_runtime_service_v3_module
from backend.conversation.domain.types_v3 import default_thread_snapshot_v3
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.services.thread_runtime_service_v3 import ThreadRuntimeServiceV3
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService


class _CaptureBroker:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, project_id: str, node_id: str, envelope: dict[str, Any], thread_role: str = "") -> None:
        del project_id, node_id, thread_role
        self.events.append(dict(envelope))


class _FakeThreadLineageService:
    def ensure_thread_binding_v2(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        workspace_root: str | None,
        *,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        del project_id, node_id, thread_role, workspace_root, base_instructions, dynamic_tools, writable_roots
        return {}


class _FakeChatService:
    def __init__(self, storage, workspace_root: Path) -> None:
        self._storage = storage
        self._workspace_root = workspace_root
        self.live_turns: set[tuple[str, str, str, str]] = set()

    def _validate_thread_access(self, project_id: str, node_id: str, thread_role: str) -> None:
        del project_id, node_id, thread_role

    def _check_thread_writable(self, project_id: str, node_id: str, thread_role: str) -> None:
        del project_id, node_id, thread_role

    def _maybe_start_local_review_for_audit_write(self, project_id: str, node_id: str) -> None:
        del project_id, node_id

    def get_session(self, project_id: str, node_id: str, thread_role: str = "ask_planning") -> dict[str, Any]:
        return self._storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)

    def _workspace_root_for_project(self, project_id: str) -> str:
        del project_id
        return str(self._workspace_root)

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        return str(project.get("project_path") or "")

    def _build_prompt_for_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        thread_role: str,
        snapshot: dict[str, Any],
        node: dict[str, Any] | None,
        node_by_id: dict[str, dict[str, Any]],
        user_content: str,
    ) -> tuple[str, str | None]:
        del project_id, node_id, turn_id, thread_role, snapshot, node, node_by_id
        return (f"prompt:{user_content}", None)

    def _mark_local_review_prompt_consumed(self, project_id: str, node_id: str) -> None:
        del project_id, node_id

    def _mark_package_review_prompt_consumed(self, project_id: str, node_id: str) -> None:
        del project_id, node_id

    def register_external_live_turn(self, project_id: str, node_id: str, thread_role: str, turn_id: str) -> None:
        self.live_turns.add((project_id, node_id, thread_role, turn_id))

    def clear_external_live_turn(self, project_id: str, node_id: str, thread_role: str, turn_id: str) -> None:
        self.live_turns.discard((project_id, node_id, thread_role, turn_id))

    def reset_session(self, project_id: str, node_id: str, thread_role: str = "ask_planning") -> dict[str, Any]:
        return self._storage.chat_state_store.clear_session(project_id, node_id, thread_role=thread_role)


class _FakeCodexClient:
    def __init__(self) -> None:
        self.raw_events: list[dict[str, Any]] = []
        self.turn_status: str = "completed"
        self.runtime_requests: dict[str, dict[str, Any]] = {}

    def get_runtime_request(self, request_id: str) -> object | None:
        return self.runtime_requests.get(request_id) if request_id in self.runtime_requests else object()

    def resolve_runtime_request_user_input(self, request_id: str, *, answers: dict[str, Any]) -> dict[str, Any] | None:
        if request_id not in self.runtime_requests:
            return None
        record = self.runtime_requests[request_id]
        record["answers"] = dict(answers)
        record["status"] = "answered"
        return record

    def run_turn_streaming(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt
        on_raw_event = kwargs.get("on_raw_event")
        thread_id = str(kwargs.get("thread_id") or "")
        for raw_event in self.raw_events:
            payload = dict(raw_event)
            payload.setdefault("thread_id", thread_id)
            if callable(on_raw_event):
                on_raw_event(payload)
        return {
            "stdout": "ok",
            "thread_id": thread_id,
            "turn_status": self.turn_status,
        }


def _build_runtime(
    storage,
    workspace_root: Path,
    *,
    thread_role: str = "execution",
) -> tuple[ThreadRuntimeServiceV3, ThreadQueryServiceV3, _CaptureBroker, str, str, _FakeChatService, _FakeCodexClient]:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    root_snapshot = storage.project_store.load_snapshot(project_id)
    node_id = root_snapshot["tree_state"]["root_node_id"]
    thread_id = f"{thread_role}-thread-1"

    registry = ThreadRegistryService(storage.thread_registry_store)
    registry.update_entry(
        project_id,
        node_id,
        thread_role,
        thread_id=thread_id,
    )
    if thread_role == "ask_planning":
        session = storage.chat_state_store.clear_session(project_id, node_id, thread_role=thread_role)
        session["thread_id"] = thread_id
        session["active_turn_id"] = None
        session["messages"] = []
        storage.chat_state_store.write_session(project_id, node_id, session, thread_role=thread_role)

    snapshot = default_thread_snapshot_v3(project_id, node_id, thread_role)
    snapshot["threadId"] = thread_id
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, thread_role, snapshot)

    codex = _FakeCodexClient()
    chat_service = _FakeChatService(storage, workspace_root)
    broker = _CaptureBroker()
    query = ThreadQueryServiceV3(
        storage=storage,
        chat_service=chat_service,
        thread_lineage_service=_FakeThreadLineageService(),
        codex_client=codex,
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        registry_service_v2=registry,
        request_ledger_service=RequestLedgerServiceV3(),
        thread_event_broker=broker,  # type: ignore[arg-type]
    )
    runtime = ThreadRuntimeServiceV3(
        storage=storage,
        tree_service=TreeService(),
        chat_service=chat_service,
        codex_client=codex,
        query_service=query,
        request_ledger_service=RequestLedgerServiceV3(),
        chat_timeout=5,
        max_message_chars=10000,
    )
    return runtime, query, broker, project_id, node_id, chat_service, codex


def test_thread_runtime_service_v3_begin_complete_lifecycle(storage, workspace_root) -> None:
    runtime, query, _, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="execution")
    snapshot = query.get_thread_snapshot(project_id, node_id, "execution")
    item = runtime._build_local_user_item(
        snapshot=snapshot,
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-test-1",
        text="hello",
    )

    started = runtime.begin_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        origin="test",
        created_items=[item],
        turn_id="turn-test-1",
    )
    assert started["processingState"] == "running"
    assert started["activeTurnId"] == "turn-test-1"

    completed = runtime.complete_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        turn_id="turn-test-1",
        outcome="completed",
    )
    assert completed["processingState"] == "idle"
    assert completed["activeTurnId"] is None


def test_thread_runtime_service_v3_start_turn_runs_to_completion(storage, workspace_root, monkeypatch) -> None:
    runtime, query, _, project_id, node_id, _, codex = _build_runtime(storage, workspace_root, thread_role="execution")
    codex.raw_events = [
        {
            "method": "item/started",
            "received_at": "2026-04-10T00:00:01Z",
            "item_id": "msg-start-1",
            "turn_id": "turn-start-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-start-1"}},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:02Z",
            "item_id": "msg-start-1",
            "turn_id": "turn-start-1",
            "params": {"delta": "done"},
        },
        {
            "method": "item/completed",
            "received_at": "2026-04-10T00:00:03Z",
            "item_id": "msg-start-1",
            "turn_id": "turn-start-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-start-1"}},
        },
        {
            "method": "turn/completed",
            "received_at": "2026-04-10T00:00:04Z",
            "turn_id": "turn-start-1",
            "params": {"turn": {"status": "completed", "id": "turn-start-1"}},
        },
    ]

    class _ImmediateThread:
        def __init__(self, *, target, kwargs, daemon):
            del daemon
            self._target = target
            self._kwargs = kwargs

        def start(self) -> None:
            self._target(**self._kwargs)

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _ImmediateThread)
    payload = runtime.start_turn(
        project_id,
        node_id,
        "execution",
        "Start this turn",
    )
    assert payload["accepted"] is True

    snapshot = query.get_thread_snapshot(project_id, node_id, "execution", publish_repairs=False)
    assert snapshot["processingState"] == "idle"
    assert snapshot["activeTurnId"] is None
    assert any(item.get("id") == "msg-start-1" for item in snapshot["items"])


def test_thread_runtime_service_v3_resolve_user_input_transitions(storage, workspace_root) -> None:
    runtime, query, _, project_id, node_id, _, codex = _build_runtime(storage, workspace_root, thread_role="execution")
    snapshot = query.get_thread_snapshot(project_id, node_id, "execution")
    snapshot["activeTurnId"] = "turn-req-1"
    snapshot["processingState"] = "waiting_user_input"
    snapshot["items"] = [
        {
            "id": "input-1",
            "kind": "userInput",
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": "turn-req-1",
            "sequence": 1,
            "createdAt": "2026-04-10T00:00:00Z",
            "updatedAt": "2026-04-10T00:00:00Z",
            "status": "requested",
            "source": "upstream",
            "tone": "info",
            "metadata": {},
            "requestId": "req-1",
            "title": None,
            "questions": [{"id": "q1", "header": None, "prompt": "Q1", "inputType": "text", "options": []}],
            "answers": [],
            "requestedAt": "2026-04-10T00:00:00Z",
            "resolvedAt": None,
        }
    ]
    snapshot["uiSignals"]["activeUserInputRequests"] = [
        {
            "requestId": "req-1",
            "itemId": "input-1",
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": "turn-req-1",
            "status": "requested",
            "createdAt": "2026-04-10T00:00:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)
    codex.runtime_requests["req-1"] = {"request_id": "req-1"}

    payload = runtime.resolve_user_input(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        request_id="req-1",
        answers=[{"questionId": "q1", "value": "yes", "label": "Yes"}],
    )
    assert payload["status"] == "answer_submitted"

    updated = query.get_thread_snapshot(project_id, node_id, "execution", publish_repairs=False)
    assert updated["processingState"] == "idle"
    assert updated["activeTurnId"] is None
    request = updated["uiSignals"]["activeUserInputRequests"][0]
    assert request["status"] == "answered"
    assert request["answers"] == [{"questionId": "q1", "value": "yes", "label": "Yes"}]


def test_thread_runtime_service_v3_emits_v3_event_types(storage, workspace_root) -> None:
    runtime, query, broker, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="execution")
    snapshot = query.get_thread_snapshot(project_id, node_id, "execution")
    item = runtime._build_local_user_item(
        snapshot=snapshot,
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-events-1",
        text="events",
    )
    runtime.begin_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        origin="test",
        created_items=[item],
        turn_id="turn-events-1",
    )
    event_types = {event.get("type") for event in broker.events}
    assert "conversation.item.upsert.v3" in event_types
    assert "thread.lifecycle.v3" in event_types


def test_thread_runtime_service_v3_no_legacy_ask_mirroring(storage, workspace_root) -> None:
    runtime, query, _, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="ask_planning")
    session_before = storage.chat_state_store.read_session(project_id, node_id, thread_role="ask_planning")
    assert session_before["messages"] == []
    snapshot = query.get_thread_snapshot(project_id, node_id, "ask_planning")
    item = runtime._build_local_user_item(
        snapshot=snapshot,
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-ask-1",
        text="ask question",
    )
    runtime.begin_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="ask_planning",
        origin="test",
        created_items=[item],
        turn_id="turn-ask-1",
    )
    runtime.complete_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="ask_planning",
        turn_id="turn-ask-1",
        outcome="completed",
    )
    session_after = storage.chat_state_store.read_session(project_id, node_id, thread_role="ask_planning")
    assert session_after["messages"] == []


def test_thread_runtime_service_v3_stream_raw_event_mapping_core_items(storage, workspace_root) -> None:
    runtime, query, _, project_id, node_id, _, codex = _build_runtime(storage, workspace_root, thread_role="execution")
    snapshot = query.get_thread_snapshot(project_id, node_id, "execution")
    user_item = runtime._build_local_user_item(
        snapshot=snapshot,
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-stream-1",
        text="run stream",
    )
    runtime.begin_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        origin="test",
        created_items=[user_item],
        turn_id="turn-stream-1",
    )
    codex.raw_events = [
        {
            "method": "item/started",
            "received_at": "2026-04-10T00:00:01Z",
            "item_id": "msg-1",
            "turn_id": "turn-stream-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:02Z",
            "item_id": "msg-1",
            "turn_id": "turn-stream-1",
            "params": {"delta": "hello"},
        },
        {
            "method": "item/completed",
            "received_at": "2026-04-10T00:00:03Z",
            "item_id": "msg-1",
            "turn_id": "turn-stream-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
        },
        {
            "method": "item/tool/call",
            "received_at": "2026-04-10T00:00:04Z",
            "call_id": "call-1",
            "turn_id": "turn-stream-1",
            "params": {"tool_name": "apply_patch", "arguments": {"path": "a.txt"}},
        },
        {
            "method": "item/started",
            "received_at": "2026-04-10T00:00:05Z",
            "item_id": "file-1",
            "turn_id": "turn-stream-1",
            "params": {"item": {"type": "fileChange", "id": "file-1", "callId": "call-1", "toolName": "apply_patch"}},
        },
        {
            "method": "item/fileChange/outputDelta",
            "received_at": "2026-04-10T00:00:06Z",
            "item_id": "file-1",
            "turn_id": "turn-stream-1",
            "params": {"delta": "preview", "files": [{"path": "preview.txt", "changeType": "created", "summary": "preview"}]},
        },
        {
            "method": "item/completed",
            "received_at": "2026-04-10T00:00:07Z",
            "item_id": "file-1",
            "turn_id": "turn-stream-1",
            "params": {
                "item": {
                    "type": "fileChange",
                    "id": "file-1",
                    "changes": [{"path": "final.txt", "kind": "modify", "summary": "final", "diff": "@@ -1 +1 @@\n-old\n+new\n"}],
                }
            },
        },
        {
            "method": "turn/completed",
            "received_at": "2026-04-10T00:00:08Z",
            "turn_id": "turn-stream-1",
            "params": {"turn": {"status": "completed", "id": "turn-stream-1"}},
        },
    ]

    result = runtime.stream_agent_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-stream-1",
        prompt="run",
        cwd=str(workspace_root),
    )
    assert result["turnStatus"] == "completed"

    updated = query.get_thread_snapshot(project_id, node_id, "execution", publish_repairs=False)
    kinds = [item.get("kind") for item in updated["items"]]
    assert "message" in kinds
    assert "diff" in kinds
    assert all(str(item.get("id") or "") != "tool-call:call-1" for item in updated["items"])
    diff_item = next(item for item in updated["items"] if item.get("kind") == "diff")
    assert diff_item["files"][0]["path"] == "final.txt"
