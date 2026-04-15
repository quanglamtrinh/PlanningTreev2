from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import backend.conversation.services.thread_runtime_service_v3 as thread_runtime_service_v3_module
from backend.conversation.domain import events as event_types
from backend.conversation.domain.types_v3 import default_thread_snapshot_v3
from backend.conversation.projector.thread_event_projector_runtime_v3 import apply_raw_event_v3
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.services.thread_runtime_service_v3 import ThreadRuntimeServiceV3, _RawEventCompactorV3
from backend.errors.app_errors import AskIdempotencyPayloadConflict
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


def test_raw_event_compactor_v3_merges_safe_delta_by_key() -> None:
    compactor = _RawEventCompactorV3(
        default_thread_id="thread-1",
        default_turn_id="turn-1",
        window_ms=50,
        max_batch_size=64,
    )
    first = {
        "method": "item/agentMessage/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "msg-1",
        "params": {"delta": "Hel"},
    }
    second = {
        "method": "item/agentMessage/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "msg-1",
        "params": {"delta": "lo"},
    }
    assert compactor.push(first) == []
    assert compactor.push(second) == []
    merged = compactor.flush()
    assert len(merged) == 1
    assert merged[0]["params"]["delta"] == "Hello"


def test_raw_event_compactor_v3_does_not_merge_cross_method() -> None:
    compactor = _RawEventCompactorV3(
        default_thread_id="thread-1",
        default_turn_id="turn-1",
        window_ms=50,
        max_batch_size=64,
    )
    first = {
        "method": "item/agentMessage/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "item-1",
        "params": {"delta": "a"},
    }
    second = {
        "method": "item/plan/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "item-1",
        "params": {"delta": "b"},
    }
    assert compactor.push(first) == []
    assert compactor.push(second) == []
    flushed = compactor.flush()
    assert [event.get("method") for event in flushed] == ["item/agentMessage/delta", "item/plan/delta"]


def test_raw_event_compactor_v3_flushes_on_boundary_event() -> None:
    compactor = _RawEventCompactorV3(
        default_thread_id="thread-1",
        default_turn_id="turn-1",
        window_ms=50,
        max_batch_size=64,
    )
    first = {
        "method": "item/fileChange/outputDelta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "diff-1",
        "params": {"delta": "part-1", "files": [{"path": "a.txt"}]},
    }
    second = {
        "method": "item/fileChange/outputDelta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "diff-1",
        "params": {"delta": "part-2", "files": [{"path": "b.txt"}]},
    }
    boundary = {
        "method": "item/completed",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "diff-1",
        "params": {},
    }
    assert compactor.push(first) == []
    assert compactor.push(second) == []
    emitted = compactor.push(boundary)
    assert len(emitted) == 2
    assert emitted[0]["method"] == "item/fileChange/outputDelta"
    assert emitted[0]["params"]["delta"] == "part-1part-2"
    assert [entry.get("path") for entry in emitted[0]["params"]["files"]] == ["a.txt", "b.txt"]
    assert emitted[1]["method"] == "item/completed"


def test_raw_event_compactor_v3_fail_open_flushes_when_clock_fails() -> None:
    calls = {"count": 0}

    def _clock() -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            return 0
        raise RuntimeError("clock failure")

    compactor = _RawEventCompactorV3(
        default_thread_id="thread-1",
        default_turn_id="turn-1",
        window_ms=50,
        max_batch_size=64,
        now_ms=_clock,
    )
    first = {
        "method": "item/agentMessage/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "msg-1",
        "params": {"delta": "a"},
    }
    second = {
        "method": "item/agentMessage/delta",
        "thread_id": "thread-1",
        "turn_id": "turn-1",
        "item_id": "msg-2",
        "params": {"delta": "b"},
    }
    assert compactor.push(first) == []
    flushed_early = compactor.push(second)
    assert len(flushed_early) == 1
    assert flushed_early[0]["item_id"] == "msg-1"
    remaining = compactor.flush()
    assert len(remaining) == 1
    assert remaining[0]["item_id"] == "msg-2"


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


def test_thread_runtime_service_v3_ask_start_turn_replays_same_key(storage, workspace_root, monkeypatch) -> None:
    runtime, query, _, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="ask_planning")

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    first = runtime.start_turn(
        project_id,
        node_id,
        "ask_planning",
        "Need help",
        metadata={"idempotencyKey": "ask-idem-1"},
    )
    second = runtime.start_turn(
        project_id,
        node_id,
        "ask_planning",
        "Need help",
        metadata={"idempotencyKey": "ask-idem-1"},
    )

    assert second == first
    snapshot = query.get_thread_snapshot(project_id, node_id, "ask_planning", publish_repairs=False)
    user_messages = [
        item
        for item in snapshot["items"]
        if str(item.get("kind") or "") == "message" and str(item.get("role") or "") == "user"
    ]
    assert len(user_messages) == 1


def test_thread_runtime_service_v3_ask_start_turn_rejects_payload_conflict(
    storage, workspace_root, monkeypatch
) -> None:
    runtime, _, _, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="ask_planning")

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    runtime.start_turn(
        project_id,
        node_id,
        "ask_planning",
        "Need help",
        metadata={"idempotencyKey": "ask-idem-1"},
    )

    with pytest.raises(AskIdempotencyPayloadConflict):
        runtime.start_turn(
            project_id,
            node_id,
            "ask_planning",
            "Need different help",
            metadata={"idempotencyKey": "ask-idem-1"},
        )


def test_thread_runtime_service_v3_start_turn_without_key_keeps_legacy_non_idempotent_behavior(
    storage, workspace_root, monkeypatch
) -> None:
    runtime, query, _, project_id, node_id, _, _ = _build_runtime(storage, workspace_root, thread_role="ask_planning")

    class _NoopThread:
        def __init__(self, *, target, kwargs, daemon):
            del target, kwargs, daemon

        def start(self) -> None:
            return

    monkeypatch.setattr(thread_runtime_service_v3_module.threading, "Thread", _NoopThread)
    first = runtime.start_turn(
        project_id,
        node_id,
        "ask_planning",
        "Need help",
    )
    second = runtime.start_turn(
        project_id,
        node_id,
        "ask_planning",
        "Need help again",
    )
    assert second["turnId"] != first["turnId"]
    snapshot = query.get_thread_snapshot(project_id, node_id, "ask_planning", publish_repairs=False)
    user_messages = [
        item
        for item in snapshot["items"]
        if str(item.get("kind") or "") == "message" and str(item.get("role") or "") == "user"
    ]
    assert len(user_messages) == 2


def test_thread_runtime_service_v3_prune_ask_idempotency_cache_ttl_and_cap_deterministic(
    storage, workspace_root
) -> None:
    runtime, _, _, _, _, _, _ = _build_runtime(storage, workspace_root, thread_role="ask_planning")
    now_ms = 5_000_000
    prefix = thread_runtime_service_v3_module._ASK_START_IDEMPOTENCY_CACHE_PREFIX
    mutation_cache: dict[str, Any] = {
        "workflow:keep": {"value": 1},
        f"{prefix}thread-1:stale": {
            "createdAtMs": now_ms - thread_runtime_service_v3_module._ASK_START_IDEMPOTENCY_TTL_MS - 10,
            "lastSeenAtMs": now_ms - thread_runtime_service_v3_module._ASK_START_IDEMPOTENCY_TTL_MS - 10,
        },
    }
    for index in range(260):
        mutation_cache[f"{prefix}thread-1:key-{index}"] = {
            "createdAtMs": now_ms - (index * 10),
            "lastSeenAtMs": now_ms - (index * 10),
        }

    changed = runtime._prune_ask_start_idempotency_cache(mutation_cache, now_ms=now_ms)
    assert changed is True
    assert "workflow:keep" in mutation_cache
    assert f"{prefix}thread-1:stale" not in mutation_cache

    ask_keys = sorted(key for key in mutation_cache.keys() if key.startswith(prefix))
    assert len(ask_keys) == thread_runtime_service_v3_module._ASK_START_IDEMPOTENCY_MAX_ENTRIES
    assert f"{prefix}thread-1:key-0" in mutation_cache
    assert f"{prefix}thread-1:key-255" in mutation_cache
    assert f"{prefix}thread-1:key-256" not in mutation_cache
    assert f"{prefix}thread-1:key-259" not in mutation_cache


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


def test_thread_runtime_service_v3_stream_compacts_message_deltas(storage, workspace_root) -> None:
    runtime, query, broker, project_id, node_id, _, codex = _build_runtime(storage, workspace_root, thread_role="execution")
    snapshot = query.get_thread_snapshot(project_id, node_id, "execution")
    user_item = runtime._build_local_user_item(
        snapshot=snapshot,
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-compact-1",
        text="compact",
    )
    runtime.begin_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        origin="test",
        created_items=[user_item],
        turn_id="turn-compact-1",
    )
    codex.raw_events = [
        {
            "method": "item/started",
            "received_at": "2026-04-10T00:00:01Z",
            "item_id": "msg-compact-1",
            "turn_id": "turn-compact-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-compact-1"}},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:02Z",
            "item_id": "msg-compact-1",
            "turn_id": "turn-compact-1",
            "params": {"delta": "hello "},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:03Z",
            "item_id": "msg-compact-1",
            "turn_id": "turn-compact-1",
            "params": {"delta": "world"},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:04Z",
            "item_id": "msg-compact-1",
            "turn_id": "turn-compact-1",
            "params": {"delta": "!"},
        },
        {
            "method": "item/completed",
            "received_at": "2026-04-10T00:00:05Z",
            "item_id": "msg-compact-1",
            "turn_id": "turn-compact-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-compact-1"}},
        },
        {
            "method": "turn/completed",
            "received_at": "2026-04-10T00:00:06Z",
            "turn_id": "turn-compact-1",
            "params": {"turn": {"status": "completed", "id": "turn-compact-1"}},
        },
    ]
    result = runtime.stream_agent_turn(
        project_id=project_id,
        node_id=node_id,
        thread_role="execution",
        thread_id=str(snapshot.get("threadId") or ""),
        turn_id="turn-compact-1",
        prompt="run",
        cwd=str(workspace_root),
    )
    assert result["turnStatus"] == "completed"

    patch_events = [
        envelope
        for envelope in broker.events
        if envelope.get("type") == event_types.CONVERSATION_ITEM_PATCH_V3
        and isinstance(envelope.get("payload"), dict)
        and str(envelope["payload"].get("itemId") or "") == "msg-compact-1"
        and isinstance(envelope["payload"].get("patch"), dict)
        and "textAppend" in envelope["payload"]["patch"]
    ]
    assert len(patch_events) == 1
    patch_payload = patch_events[0]["payload"]["patch"]
    assert patch_payload["textAppend"] == "hello world!"

    updated = query.get_thread_snapshot(project_id, node_id, "execution", publish_repairs=False)
    message_item = next(item for item in updated["items"] if str(item.get("id") or "") == "msg-compact-1")
    assert message_item["text"] == "hello world!"


def test_raw_event_compactor_v3_compacted_and_non_compacted_projection_match() -> None:
    raw_events: list[dict[str, Any]] = [
        {
            "method": "item/started",
            "received_at": "2026-04-10T00:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "msg-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:02Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "msg-1",
            "params": {"delta": "Hel"},
        },
        {
            "method": "item/agentMessage/delta",
            "received_at": "2026-04-10T00:00:02Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "msg-1",
            "params": {"delta": "lo"},
        },
        {
            "method": "item/completed",
            "received_at": "2026-04-10T00:00:03Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "msg-1",
            "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
        },
        {
            "method": "item/tool/requestUserInput",
            "received_at": "2026-04-10T00:00:04Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "input-1",
            "request_id": "req-1",
            "params": {
                "questions": [
                    {
                        "id": "q1",
                        "header": "Confirm",
                        "prompt": "Proceed?",
                        "inputType": "single_select",
                        "options": [{"label": "Yes", "description": None}],
                    }
                ]
            },
        },
        {
            "method": "serverRequest/resolved",
            "received_at": "2026-04-10T00:00:05Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "input-1",
            "request_id": "req-1",
            "params": {
                "answers": [{"questionId": "q1", "value": "yes", "label": "Yes"}],
                "resolved_at": "2026-04-10T00:00:05Z",
            },
        },
        {
            "method": "thread/status/changed",
            "received_at": "2026-04-10T00:00:06Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "params": {"status": {"type": "running"}},
        },
        {
            "method": "turn/completed",
            "received_at": "2026-04-10T00:00:07Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "params": {"turn": {"status": "completed", "id": "turn-1"}},
        },
    ]

    compactor = _RawEventCompactorV3(
        default_thread_id="thread-1",
        default_turn_id="turn-1",
        window_ms=50,
        max_batch_size=64,
    )
    compacted_events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        compacted_events.extend(compactor.push(raw_event))
    compacted_events.extend(compactor.flush())

    direct_snapshot = default_thread_snapshot_v3("project-1", "node-1", "execution")
    direct_snapshot["threadId"] = "thread-1"
    direct_snapshot["activeTurnId"] = "turn-1"
    direct_snapshot["processingState"] = "running"
    for raw_event in raw_events:
        direct_snapshot, _ = apply_raw_event_v3(direct_snapshot, raw_event)

    compacted_snapshot = default_thread_snapshot_v3("project-1", "node-1", "execution")
    compacted_snapshot["threadId"] = "thread-1"
    compacted_snapshot["activeTurnId"] = "turn-1"
    compacted_snapshot["processingState"] = "running"
    for raw_event in compacted_events:
        compacted_snapshot, _ = apply_raw_event_v3(compacted_snapshot, raw_event)

    compacted_snapshot["createdAt"] = direct_snapshot["createdAt"]
    compacted_snapshot["updatedAt"] = direct_snapshot["updatedAt"]
    assert direct_snapshot == compacted_snapshot
