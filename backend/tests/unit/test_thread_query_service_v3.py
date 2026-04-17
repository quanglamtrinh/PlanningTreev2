from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.domain.types_v3 import default_thread_snapshot_v3
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_actor_runtime_v3 import ThreadActorRuntimeV3
from backend.conversation.services.thread_checkpoint_policy_v3 import ThreadCheckpointPolicyV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.errors.app_errors import ConversationStreamMismatch, ConversationV3Missing
from backend.services.project_service import ProjectService


class _FakeChatService:
    def __init__(self, storage, workspace_root: Path) -> None:
        self._storage = storage
        self._workspace_root = workspace_root
        self.live_turns: set[tuple[str, str, str, str]] = set()

    def _validate_thread_access(self, project_id: str, node_id: str, thread_role: str) -> None:
        del project_id, node_id, thread_role

    def get_session(self, project_id: str, node_id: str, thread_role: str = "ask_planning") -> dict[str, Any]:
        return self._storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)

    def _workspace_root_for_project(self, project_id: str) -> str:
        del project_id
        return str(self._workspace_root)

    def has_live_turn(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        turn_id: str | None = None,
    ) -> bool:
        if turn_id is not None:
            return (project_id, node_id, thread_role, str(turn_id)) in self.live_turns
        return any(
            turn[0] == project_id and turn[1] == node_id and turn[2] == thread_role
            for turn in self.live_turns
        )

    def reset_session(self, project_id: str, node_id: str, thread_role: str = "ask_planning") -> dict[str, Any]:
        return self._storage.chat_state_store.clear_session(project_id, node_id, thread_role=thread_role)


class _FakeThreadLineageService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        resume_guarded: bool = False,
        force_resume: bool = False,
        active_turn_live: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "project_id": project_id,
                "node_id": node_id,
                "thread_role": thread_role,
                "workspace_root": workspace_root,
                "base_instructions": base_instructions,
                "dynamic_tools": dynamic_tools,
                "writable_roots": writable_roots,
                "resume_guarded": resume_guarded,
                "force_resume": force_resume,
                "active_turn_live": active_turn_live,
            }
        )
        return {}


class _FakeCodexClient:
    def get_runtime_request(self, request_id: str) -> object | None:
        del request_id
        return object()


class _CaptureBroker:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, project_id: str, node_id: str, envelope: dict[str, Any], thread_role: str = "") -> None:
        del project_id, node_id, thread_role
        self.events.append(dict(envelope))


def _build_service(
    storage,
    workspace_root: Path,
    *,
    broker: _CaptureBroker | None = None,
    thread_actor_mode: str = "off",
) -> tuple[ThreadQueryServiceV3, str, str]:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    root_snapshot = storage.project_store.load_snapshot(project_id)
    node_id = root_snapshot["tree_state"]["root_node_id"]
    registry = ThreadRegistryService(storage.thread_registry_store)
    registry.update_entry(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
    )
    capture = broker or _CaptureBroker()
    service = ThreadQueryServiceV3(
        storage=storage,
        chat_service=_FakeChatService(storage, workspace_root),
        thread_lineage_service=_FakeThreadLineageService(),
        codex_client=_FakeCodexClient(),
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        registry_service_v2=registry,
        request_ledger_service=RequestLedgerServiceV3(),
        thread_event_broker=capture,  # type: ignore[arg-type]
        mini_journal_store_v3=storage.thread_mini_journal_store_v3,
        event_log_store_v3=storage.thread_event_log_store_v3,
        checkpoint_policy_v3=ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000),
        actor_runtime_v3=ThreadActorRuntimeV3(),
        thread_actor_mode=thread_actor_mode,
        log_compact_min_events=2,
    )
    return service, project_id, node_id


def test_get_thread_snapshot_v3_reads_existing_v3_snapshot(storage, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    snapshot["snapshotVersion"] = 4
    snapshot["items"] = [
        {
            "id": "msg-v3",
            "kind": "message",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-10T00:00:00Z",
            "updatedAt": "2026-04-10T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "from v3",
            "format": "markdown",
        }
    ]
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    legacy = default_thread_snapshot(project_id, node_id, "execution")
    legacy["threadId"] = "legacy-thread"
    legacy["items"] = [
        {
            "id": "msg-v2",
            "kind": "message",
            "threadId": "legacy-thread",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-10T00:00:00Z",
            "updatedAt": "2026-04-10T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "from v2",
            "format": "markdown",
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", legacy)

    loaded = service.get_thread_snapshot(project_id, node_id, "execution")

    assert loaded["items"][0]["id"] == "msg-v3"
    assert loaded["threadRole"] == "execution"
    assert "lane" not in loaded


def test_get_thread_snapshot_v3_bridge_enabled_reads_through_and_persists(storage, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    legacy = default_thread_snapshot(project_id, node_id, "execution")
    legacy["threadId"] = "execution-thread-1"
    legacy["snapshotVersion"] = 3
    legacy["items"] = [
        {
            "id": "msg-v2",
            "kind": "message",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-10T00:00:00Z",
            "updatedAt": "2026-04-10T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "legacy bridge",
            "format": "markdown",
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", legacy)

    loaded = service.get_thread_snapshot(project_id, node_id, "execution")
    persisted = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, "execution")

    assert loaded["items"][0]["id"] == "msg-v2"
    assert loaded["threadRole"] == "execution"
    assert loaded["snapshotVersion"] == persisted["snapshotVersion"]
    assert storage.thread_snapshot_store_v3.exists(project_id, node_id, "execution") is True


def test_get_thread_snapshot_v3_bridge_allowlist_respects_project_gate(storage, workspace_root, monkeypatch) -> None:
    service, project_id, node_id = _build_service(storage, workspace_root)
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "allowlist")
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", "other-project")
    with pytest.raises(ConversationV3Missing):
        service.get_thread_snapshot(project_id, node_id, "execution")

    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", project_id)
    legacy = default_thread_snapshot(project_id, node_id, "execution")
    legacy["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", legacy)
    loaded = service.get_thread_snapshot(project_id, node_id, "execution")
    assert loaded["threadRole"] == "execution"


def test_get_thread_snapshot_v3_bridge_disabled_raises_typed_error(storage, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "disabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    with pytest.raises(ConversationV3Missing):
        service.get_thread_snapshot(project_id, node_id, "execution")


def test_get_thread_snapshot_v3_never_back_writes_v2(storage, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    legacy = default_thread_snapshot(project_id, node_id, "execution")
    legacy["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, "execution", legacy)

    def _forbidden_write(*args, **kwargs):
        raise AssertionError("V2 write should never be called from V3 bridge.")

    storage.thread_snapshot_store_v2.write_snapshot = _forbidden_write  # type: ignore[method-assign]
    loaded = service.get_thread_snapshot(project_id, node_id, "execution")
    assert loaded["threadRole"] == "execution"


def test_build_stream_snapshot_v3_guard_raises_mismatch(storage, workspace_root, monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    snapshot["snapshotVersion"] = 2
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    with pytest.raises(ConversationStreamMismatch):
        service.build_stream_snapshot(
            project_id,
            node_id,
            "execution",
            after_snapshot_version=99,
        )


def test_get_thread_snapshot_v3_execution_binding_uses_guarded_resume_flags(
    storage,
    workspace_root,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    service.get_thread_snapshot(project_id, node_id, "execution")

    calls = service._thread_lineage_service.calls  # type: ignore[attr-defined]
    assert calls
    assert calls[-1]["thread_role"] == "execution"
    assert calls[-1]["resume_guarded"] is True
    assert calls[-1]["force_resume"] is False
    assert calls[-1]["active_turn_live"] is False


def test_get_thread_snapshot_v3_execution_binding_passes_live_turn_state(
    storage,
    workspace_root,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)
    service._chat_service.live_turns.add((project_id, node_id, "execution", "turn-ext-1"))  # type: ignore[attr-defined]

    service.get_thread_snapshot(project_id, node_id, "execution")

    calls = service._thread_lineage_service.calls  # type: ignore[attr-defined]
    assert calls
    assert calls[-1]["active_turn_live"] is True


def test_get_thread_snapshot_v3_ask_fast_read_skips_session_hydration(
    storage,
    workspace_root,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "enabled")
    service, project_id, node_id = _build_service(storage, workspace_root)
    registry = ThreadRegistryService(storage.thread_registry_store)
    registry.update_entry(
        project_id,
        node_id,
        "ask_planning",
        thread_id="ask-thread-fast-read",
    )

    snapshot = default_thread_snapshot_v3(project_id, node_id, "ask_planning")
    snapshot["threadId"] = "ask-thread-fast-read"
    snapshot["snapshotVersion"] = 5
    snapshot["processingState"] = "idle"
    snapshot["activeTurnId"] = None
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "ask_planning", snapshot)

    ask_session = storage.chat_state_store.read_session(project_id, node_id, thread_role="ask_planning")
    ask_session["thread_id"] = "ask-thread-fast-read"
    ask_session["active_turn_id"] = "ask-turn-1"
    storage.chat_state_store.write_session(project_id, node_id, ask_session, thread_role="ask_planning")

    def _forbidden_get_session(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("ask fast-read path should not call chat_service.get_session")

    service._chat_service.get_session = _forbidden_get_session  # type: ignore[method-assign]

    loaded = service.get_thread_snapshot(
        project_id,
        node_id,
        "ask_planning",
        allow_thread_read_hydration=False,
    )

    assert loaded["threadId"] == "ask-thread-fast-read"
    assert loaded["activeTurnId"] == "ask-turn-1"
    assert loaded["processingState"] == "running"


def test_issue_stream_event_id_v3_is_monotonic_and_durable(storage, workspace_root) -> None:
    service, project_id, node_id = _build_service(storage, workspace_root)

    first = service.issue_stream_event_id(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
    )
    second = service.issue_stream_event_id(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
    )
    assert first == "1"
    assert second == "2"

    restarted_service, _, _ = _build_service(storage, workspace_root)
    third = restarted_service.issue_stream_event_id(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
    )
    assert third == "3"


def test_issue_stream_event_id_v3_scopes_sequence_per_thread(storage, workspace_root) -> None:
    service, project_id, node_id = _build_service(storage, workspace_root)

    assert (
        service.issue_stream_event_id(
            project_id,
            node_id,
            "execution",
            thread_id="execution-thread-1",
        )
        == "1"
    )
    assert (
        service.issue_stream_event_id(
            project_id,
            node_id,
            "execution",
            thread_id="execution-thread-1",
        )
        == "2"
    )
    assert (
        service.issue_stream_event_id(
            project_id,
            node_id,
            "execution",
            thread_id="execution-thread-2",
        )
        == "1"
    )


def test_persist_thread_mutation_v3_suppresses_duplicate_lifecycle_noop(storage, workspace_root) -> None:
    broker = _CaptureBroker()
    service, project_id, node_id = _build_service(storage, workspace_root, broker=broker)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    lifecycle_event = {
        "type": event_types.THREAD_LIFECYCLE_V3,
        "payload": {
            "state": event_types.TURN_COMPLETED,
            "processingState": "idle",
            "activeTurnId": None,
            "detail": None,
        },
    }

    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", snapshot, [lifecycle_event])
    service.persist_thread_mutation(project_id, node_id, "execution", updated, [lifecycle_event])

    lifecycle_envelopes = [
        envelope for envelope in broker.events if envelope.get("type") == event_types.THREAD_LIFECYCLE_V3
    ]
    assert len(lifecycle_envelopes) == 1


def test_persist_thread_mutation_v3_suppresses_terminal_duplicate_for_same_turn(storage, workspace_root) -> None:
    broker = _CaptureBroker()
    service, project_id, node_id = _build_service(storage, workspace_root, broker=broker)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    terminal_event = {
        "type": event_types.THREAD_LIFECYCLE_V3,
        "payload": {
            "state": event_types.TURN_COMPLETED,
            "processingState": "idle",
            "activeTurnId": "turn-dup-1",
            "detail": None,
        },
    }
    started_event = {
        "type": event_types.THREAD_LIFECYCLE_V3,
        "payload": {
            "state": event_types.TURN_STARTED,
            "processingState": "running",
            "activeTurnId": "turn-dup-1",
            "detail": None,
        },
    }

    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", snapshot, [terminal_event])
    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", updated, [started_event])
    service.persist_thread_mutation(project_id, node_id, "execution", updated, [terminal_event])

    lifecycle_envelopes = [
        envelope for envelope in broker.events if envelope.get("type") == event_types.THREAD_LIFECYCLE_V3
    ]
    assert len(lifecycle_envelopes) == 2
    assert [envelope["payload"]["state"] for envelope in lifecycle_envelopes] == [
        event_types.TURN_COMPLETED,
        event_types.TURN_STARTED,
    ]


def test_persist_thread_mutation_v3_never_suppresses_non_lifecycle_events(storage, workspace_root) -> None:
    broker = _CaptureBroker()
    service, project_id, node_id = _build_service(storage, workspace_root, broker=broker)
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    patch_event = {
        "type": event_types.CONVERSATION_ITEM_PATCH_V3,
        "payload": {
            "itemId": "item-1",
            "patch": {"kind": "message", "textAppend": "x"},
        },
    }

    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", snapshot, [patch_event])
    service.persist_thread_mutation(project_id, node_id, "execution", updated, [patch_event])

    patch_envelopes = [
        envelope for envelope in broker.events if envelope.get("type") == event_types.CONVERSATION_ITEM_PATCH_V3
    ]
    assert len(patch_envelopes) == 2


def test_persist_thread_mutation_v3_actor_on_splits_publish_and_checkpoint(storage, workspace_root) -> None:
    broker = _CaptureBroker()
    service, project_id, node_id = _build_service(
        storage,
        workspace_root,
        broker=broker,
        thread_actor_mode="on",
    )
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    snapshot["snapshotVersion"] = 0
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    patch_event = {
        "type": event_types.CONVERSATION_ITEM_PATCH_V3,
        "payload": {
            "itemId": "item-1",
            "patch": {"kind": "message", "textAppend": "x"},
        },
    }
    first_updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", snapshot, [patch_event])
    persisted_after_patch = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, "execution")

    assert int(first_updated["snapshotVersion"]) == 1
    assert int(persisted_after_patch["snapshotVersion"]) == 0

    lifecycle_event = {
        "type": event_types.THREAD_LIFECYCLE_V3,
        "payload": {
            "state": event_types.WAITING_USER_INPUT,
            "processingState": "waiting_user_input",
            "activeTurnId": "turn-1",
            "detail": None,
        },
    }
    second_updated, _ = service.persist_thread_mutation(
        project_id,
        node_id,
        "execution",
        first_updated,
        [lifecycle_event],
    )
    persisted_after_boundary = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, "execution")

    assert int(second_updated["snapshotVersion"]) == 2
    assert int(persisted_after_boundary["snapshotVersion"]) == 2

    journal_tail = storage.thread_mini_journal_store_v3.read_tail_after(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=0,
    )
    event_log_tail = storage.thread_event_log_store_v3.read_tail_after_log_seq(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=0,
    )
    assert len(journal_tail) == 1
    assert journal_tail[0]["boundaryType"] == "waiting_user_input"
    assert event_log_tail == []


def test_get_thread_snapshot_v3_actor_on_replays_event_log_tail(storage, workspace_root) -> None:
    service, project_id, node_id = _build_service(
        storage,
        workspace_root,
        thread_actor_mode="on",
    )
    baseline_snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    baseline_snapshot["threadId"] = "execution-thread-1"
    baseline_snapshot["snapshotVersion"] = 0
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", baseline_snapshot)

    next_snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    next_snapshot["threadId"] = "execution-thread-1"
    next_snapshot["snapshotVersion"] = 0
    next_snapshot["items"] = [
        {
            "id": "msg-log-1",
            "kind": "message",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-12T00:00:00Z",
            "updatedAt": "2026-04-12T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "Recovered from log",
            "format": "markdown",
        }
    ]
    upsert_event = {
        "type": event_types.CONVERSATION_ITEM_UPSERT_V3,
        "payload": {
            "item": next_snapshot["items"][0],
        },
    }

    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", next_snapshot, [upsert_event])
    persisted_snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, "execution")
    assert int(updated["snapshotVersion"]) == 1
    assert int(persisted_snapshot["snapshotVersion"]) == 0

    restarted_service = ThreadQueryServiceV3(
        storage=storage,
        chat_service=_FakeChatService(storage, workspace_root),
        thread_lineage_service=_FakeThreadLineageService(),
        codex_client=_FakeCodexClient(),
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        registry_service_v2=ThreadRegistryService(storage.thread_registry_store),
        request_ledger_service=RequestLedgerServiceV3(),
        thread_event_broker=_CaptureBroker(),  # type: ignore[arg-type]
        mini_journal_store_v3=storage.thread_mini_journal_store_v3,
        event_log_store_v3=storage.thread_event_log_store_v3,
        checkpoint_policy_v3=ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000),
        actor_runtime_v3=ThreadActorRuntimeV3(),
        thread_actor_mode="on",
        log_compact_min_events=2,
    )
    recovered = restarted_service.get_thread_snapshot(project_id, node_id, "execution")
    assert int(recovered["snapshotVersion"]) == 1
    assert any(str(item.get("id") or "") == "msg-log-1" for item in recovered.get("items", []))


def test_get_thread_snapshot_v3_actor_on_fails_closed_on_journal_gap(storage, workspace_root) -> None:
    service, project_id, node_id = _build_service(
        storage,
        workspace_root,
        thread_actor_mode="on",
    )
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    snapshot["snapshotVersion"] = 7
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    storage.thread_mini_journal_store_v3.append_boundary_record(
        project_id,
        node_id,
        "execution",
        {
            "journalSeq": 1,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "eventIdStart": 10,
            "eventIdEnd": 12,
            "boundaryType": "turn_completed",
            "snapshotVersionAtWrite": 7,
            "createdAt": "2026-04-12T00:00:00Z",
        },
    )
    storage.thread_mini_journal_store_v3.append_boundary_record(
        project_id,
        node_id,
        "execution",
        {
            "journalSeq": 3,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "turnId": "turn-2",
            "eventIdStart": 13,
            "eventIdEnd": 14,
            "boundaryType": "turn_completed",
            "snapshotVersionAtWrite": 7,
            "createdAt": "2026-04-12T00:00:01Z",
        },
    )

    with pytest.raises(ValueError):
        service.get_thread_snapshot(project_id, node_id, "execution")


def test_persist_thread_mutation_v3_shadow_keeps_legacy_authoritative(storage, workspace_root) -> None:
    broker = _CaptureBroker()
    service, project_id, node_id = _build_service(
        storage,
        workspace_root,
        broker=broker,
        thread_actor_mode="shadow",
    )
    snapshot = default_thread_snapshot_v3(project_id, node_id, "execution")
    snapshot["threadId"] = "execution-thread-1"
    snapshot["snapshotVersion"] = 0
    storage.thread_snapshot_store_v3.write_snapshot(project_id, node_id, "execution", snapshot)

    patch_event = {
        "type": event_types.CONVERSATION_ITEM_PATCH_V3,
        "payload": {
            "itemId": "item-1",
            "patch": {"kind": "message", "textAppend": "x"},
        },
    }
    updated, _ = service.persist_thread_mutation(project_id, node_id, "execution", snapshot, [patch_event])
    persisted = storage.thread_snapshot_store_v3.read_snapshot(project_id, node_id, "execution")
    journal_tail = storage.thread_mini_journal_store_v3.read_tail_after(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=0,
    )

    assert int(updated["snapshotVersion"]) == 1
    assert int(persisted["snapshotVersion"]) == 1
    assert journal_tail == []
