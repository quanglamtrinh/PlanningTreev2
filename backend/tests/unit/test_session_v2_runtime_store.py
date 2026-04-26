from __future__ import annotations

import shutil
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2

_DAY_MS = 24 * 60 * 60 * 1000


@contextmanager
def _workspace_temp_dir() -> Iterator[Path]:
    root = Path("pytest_tmp_dir") / "session_v2_runtime_store" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_runtime_store_event_replay_and_cursor_errors() -> None:
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
        store = RuntimeStoreV2(
            db_path=db_path,
            retention_max_events=2,
            retention_days=1,
            subscriber_queue_capacity=2,
        )
        try:
            old_now = 1_700_000_000_000
            store._now_ms = lambda: old_now  # type: ignore[method-assign] # noqa: SLF001
            store.append_notification(method="thread/started", params={"threadId": "thread-1"})
            store.append_notification(method="thread/status/changed", params={"threadId": "thread-1"})
            store.append_notification(method="thread/closed", params={"threadId": "thread-1"})
            store._now_ms = lambda: old_now + (2 * _DAY_MS)  # type: ignore[method-assign] # noqa: SLF001
            store.append_notification(method="thread/started", params={"threadId": "thread-1"})

            replay = store.replay_events(thread_id="thread-1", cursor_value=2)
            assert [event["eventSeq"] for event in replay] == [3, 4]
            assert all(event["source"] == "replay" for event in replay)

            with pytest.raises(SessionCoreError) as invalid_exc:
                store.parse_cursor(thread_id="thread-1", cursor="abc")
            assert invalid_exc.value.code == "ERR_CURSOR_INVALID"

            with pytest.raises(SessionCoreError) as expired_exc:
                store.parse_cursor(thread_id="thread-1", cursor="1")
            assert expired_exc.value.code == "ERR_CURSOR_EXPIRED"
            details = expired_exc.value.details
            assert isinstance(details.get("snapshotPointer"), dict)
            snapshot_pointer = details["snapshotPointer"]
            assert "snapshotVersion" in snapshot_pointer
            assert "lastEventSeq" in snapshot_pointer
            assert "updatedAtMs" in snapshot_pointer
        finally:
            store.close()


def test_runtime_store_subscriber_lagged_behavior_is_bounded() -> None:
    store = RuntimeStoreV2(subscriber_queue_capacity=1, retention_max_events=100)
    subscriber_id = store.subscribe_thread_events(thread_id="thread-1")
    store.append_notification(method="thread/started", params={"threadId": "thread-1"})
    store.append_notification(method="thread/status/changed", params={"threadId": "thread-1"})
    store.append_notification(method="thread/closed", params={"threadId": "thread-1"})

    maybe_event = store.read_subscriber_event(subscriber_id=subscriber_id, timeout_sec=0.5)
    if isinstance(maybe_event, dict) and maybe_event:
        assert "__control" in maybe_event or "eventSeq" in maybe_event

    metrics = store.metrics_snapshot()
    assert metrics["laggedResetCount"] >= 1
    # Tier-0 lag should not be treated as transport-drop data loss.
    assert metrics["dropCountsByTier"].get("tier0", 0) == 0


def test_runtime_store_snapshot_payload_and_tier0_cadence() -> None:
    store = RuntimeStoreV2()
    store.append_notification(method="thread/started", params={"threadId": "thread-1"})
    assert store._snapshot_versions["thread-1"] == 1  # noqa: SLF001

    # Pin snapshot clock so cadence is controlled by tier-0 count.
    store._snapshot_last_ms["thread-1"] = store._now_ms()  # noqa: SLF001
    for i in range(199):
        store.append_notification(
            method="item/agentMessage/delta",
            params={"threadId": "thread-1", "turnId": "turn-1", "delta": str(i)},
        )
    assert store._snapshot_versions["thread-1"] == 1  # noqa: SLF001

    store.append_notification(
        method="item/agentMessage/delta",
        params={"threadId": "thread-1", "turnId": "turn-1", "delta": "trigger"},
    )
    assert store._snapshot_versions["thread-1"] == 2  # noqa: SLF001
    payload = store._snapshot_payloads["thread-1"]  # noqa: SLF001
    assert "thread" in payload
    assert "turnIndex" in payload
    assert "itemIndex" in payload
    assert "pendingRequestIndex" in payload
    assert "lastEventSeq" in payload
    assert isinstance(payload["pendingRequestIndex"], dict)


def test_runtime_store_classifies_terminal_interaction_as_tier1() -> None:
    store = RuntimeStoreV2()

    event = store.append_notification(
        method="item/commandExecution/terminalInteraction",
        params={"threadId": "thread-1", "turnId": "turn-1", "itemId": "cmd-1", "stdin": "y\n"},
    )

    assert event["tier"] == "tier1"


def test_runtime_store_pre_event_observer_does_not_hold_runtime_lock() -> None:
    store = RuntimeStoreV2()
    observer_entered = threading.Event()
    release_observer = threading.Event()

    def blocking_observer(_event: dict) -> None:
        observer_entered.set()
        assert release_observer.wait(timeout=2)

    store.add_pre_event_observer(blocking_observer)

    worker = threading.Thread(
        target=lambda: store.append_notification(method="thread/started", params={"threadId": "thread-1"}),
        daemon=True,
    )
    worker.start()
    assert observer_entered.wait(timeout=1)

    # The rollout write-through hook may block on filesystem/native I/O, but it
    # must not freeze read paths that need the runtime lock.
    assert store.get_journal_head("thread-1")["lastEventSeq"] == 1

    release_observer.set()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_runtime_store_dual_floor_retention_prunes_only_when_old_and_overflow() -> None:
    store = RuntimeStoreV2(retention_max_events=2, retention_days=7)

    old_now = 2_000_000_000_000
    store._now_ms = lambda: old_now  # type: ignore[method-assign] # noqa: SLF001
    store.append_notification(method="thread/started", params={"threadId": "thread-1"})
    store.append_notification(method="thread/status/changed", params={"threadId": "thread-1"})
    store.append_notification(method="thread/closed", params={"threadId": "thread-1"})
    # Overflow alone is not enough when events are still within age floor.
    assert len(store.read_thread_journal("thread-1")) == 3

    advanced_now = old_now + (9 * _DAY_MS)
    store._now_ms = lambda: advanced_now  # type: ignore[method-assign] # noqa: SLF001
    store.append_notification(method="thread/started", params={"threadId": "thread-1"})
    # Once events are old enough and overflowed, retention trims to event floor.
    journal = store.read_thread_journal("thread-1")
    assert len(journal) == 2
    assert [event["eventSeq"] for event in journal] == [3, 4]


def test_runtime_store_pending_request_lifecycle_and_turn_wait_resume() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")

    pending = store.register_pending_server_request(
        raw_request_id=123,
        method="item/tool/requestUserInput",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        payload={"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1"},
    )
    assert pending["status"] == "pending"
    assert store.get_turn(thread_id="thread-1", turn_id="turn-1")["status"] == "waitingUserInput"
    created_events = [event for event in store.read_thread_journal("thread-1") if event["method"] == "serverRequest/created"]
    assert len(created_events) == 1
    assert created_events[0]["tier"] == "tier0"
    assert created_events[0]["params"]["request"]["requestId"] == pending["requestId"]
    assert created_events[0]["params"]["request"]["status"] == "pending"

    submitted = store.mark_pending_server_request_submitted(request_id=pending["requestId"], submission_kind="resolve")
    assert submitted["status"] == "submitted"
    updated_events = [event for event in store.read_thread_journal("thread-1") if event["method"] == "serverRequest/updated"]
    assert len(updated_events) == 1
    assert updated_events[0]["tier"] == "tier0"
    assert updated_events[0]["params"]["request"]["requestId"] == pending["requestId"]
    assert updated_events[0]["params"]["request"]["status"] == "submitted"

    resolved = store.resolve_pending_server_request_from_notification(thread_id="thread-1", raw_request_id=123)
    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert store.list_pending_server_requests() == []
    assert store.get_turn(thread_id="thread-1", turn_id="turn-1")["status"] == "inProgress"


def test_runtime_store_append_turn_started_if_absent_is_idempotent() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")

    first = store.append_turn_started_if_absent(
        thread_id="thread-1",
        turn_id="turn-1",
        turn={"id": "turn-1", "status": "inProgress", "items": []},
    )
    second = store.append_turn_started_if_absent(
        thread_id="thread-1",
        turn_id="turn-1",
        turn={"id": "turn-1", "status": "inProgress", "items": []},
    )

    assert first["eventSeq"] == second["eventSeq"]
    journal = store.read_thread_journal("thread-1")
    assert [event.get("method") for event in journal].count("turn/started") == 1


def test_runtime_store_turn_started_notification_dedupes_existing_turn_started_event() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")
    store.append_turn_started_if_absent(
        thread_id="thread-1",
        turn_id="turn-1",
        turn={"id": "turn-1", "status": "inProgress", "items": []},
    )

    store.append_notification(
        method="turn/started",
        params={"threadId": "thread-1", "turn": {"id": "turn-1", "status": "inProgress", "items": []}},
    )

    journal = store.read_thread_journal("thread-1")
    assert [event.get("method") for event in journal].count("turn/started") == 1


def test_runtime_store_pending_request_events_dedupe_and_enriched_resolved() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")
    first = store.register_pending_server_request(
        raw_request_id=123,
        method="item/tool/requestUserInput",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        payload={"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1"},
    )
    duplicate_pending = store.register_pending_server_request(
        raw_request_id=123,
        method="item/tool/requestUserInput",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        payload={"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1"},
    )
    assert duplicate_pending["requestId"] == first["requestId"]

    submitted = store.mark_pending_server_request_submitted(request_id=first["requestId"], submission_kind="resolve")
    assert submitted["status"] == "submitted"
    duplicate_submitted = store.register_pending_server_request(
        raw_request_id=123,
        method="item/tool/requestUserInput",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        payload={"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1"},
    )
    assert duplicate_submitted["requestId"] == first["requestId"]

    journal = store.read_thread_journal("thread-1")
    assert [event["method"] for event in journal].count("serverRequest/created") == 1
    assert [event["method"] for event in journal].count("serverRequest/updated") == 1

    resolved_event = store.append_notification(
        method="serverRequest/resolved",
        params={"threadId": "thread-1", "requestId": 123},
    )
    assert resolved_event["method"] == "serverRequest/resolved"
    assert resolved_event["tier"] == "tier0"
    assert resolved_event["params"]["request"]["requestId"] == first["requestId"]
    assert resolved_event["params"]["request"]["status"] == "resolved"
    assert store.list_pending_server_requests() == []


def test_runtime_store_resolved_notification_without_submit_expires_request() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")
    pending = store.register_pending_server_request(
        raw_request_id="req-1",
        method="item/commandExecution/requestApproval",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id="item-1",
        payload={"threadId": "thread-1", "turnId": "turn-1", "itemId": "item-1"},
    )

    resolved = store.resolve_pending_server_request_from_notification(thread_id="thread-1", raw_request_id="req-1")
    assert resolved is not None
    assert resolved["requestId"] == pending["requestId"]
    assert resolved["status"] == "expired"
    assert store.list_pending_server_requests() == []
    assert store.get_turn(thread_id="thread-1", turn_id="turn-1")["status"] == "inProgress"


def test_runtime_store_expire_pending_on_reinit_allows_raw_request_id_reuse() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="inProgress")
    first = store.register_pending_server_request(
        raw_request_id=7,
        method="item/fileChange/requestApproval",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id=None,
        payload={"threadId": "thread-1", "turnId": "turn-1"},
    )
    expired_count = store.expire_pending_server_requests_for_new_session()
    assert expired_count == 1
    assert store.get_pending_server_request(request_id=first["requestId"])["status"] == "expired"
    updated_events = [event for event in store.read_thread_journal("thread-1") if event["method"] == "serverRequest/updated"]
    assert len(updated_events) == 1
    assert updated_events[0]["params"]["request"]["requestId"] == first["requestId"]
    assert updated_events[0]["params"]["request"]["status"] == "expired"

    second = store.register_pending_server_request(
        raw_request_id=7,
        method="item/fileChange/requestApproval",
        thread_id="thread-1",
        turn_id="turn-1",
        item_id=None,
        payload={"threadId": "thread-1", "turnId": "turn-1"},
    )
    assert second["requestId"] != first["requestId"]
    assert second["status"] == "pending"


def test_runtime_store_pending_requests_persist_and_restore() -> None:
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
        store = RuntimeStoreV2(db_path=db_path)
        pending = store.register_pending_server_request(
            raw_request_id=999,
            method="item/permissions/requestApproval",
            thread_id="thread-1",
            turn_id="turn-1",
            item_id=None,
            payload={"threadId": "thread-1", "turnId": "turn-1"},
        )
        store.mark_pending_server_request_submitted(request_id=pending["requestId"], submission_kind="reject")
        store.close()

        reopened = RuntimeStoreV2(db_path=db_path)
        try:
            restored = reopened.get_pending_server_request(request_id=pending["requestId"])
            assert restored is not None
            assert restored["status"] == "submitted"
            assert reopened.pending_server_request_raw_id(request_id=pending["requestId"]) == 999
        finally:
            reopened.close()


def test_runtime_store_mcp_pending_request_keeps_nullable_turn_id() -> None:
    store = RuntimeStoreV2()
    pending = store.register_pending_server_request(
        raw_request_id="mcp-1",
        method="mcpServer/elicitation/request",
        thread_id="thread-1",
        turn_id=None,
        item_id="mcp-item-1",
        payload={"threadId": "thread-1", "itemId": "mcp-item-1"},
    )
    assert pending["turnId"] is None
    listed = store.list_pending_server_requests()
    assert listed[0]["turnId"] is None


def test_runtime_store_pending_request_nullable_turn_id_persists_and_restores() -> None:
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
        store = RuntimeStoreV2(db_path=db_path)
        pending = store.register_pending_server_request(
            raw_request_id="mcp-restore",
            method="mcpServer/elicitation/request",
            thread_id="thread-1",
            turn_id=None,
            item_id=None,
            payload={"threadId": "thread-1"},
        )
        store.close()

        reopened = RuntimeStoreV2(db_path=db_path)
        try:
            restored = reopened.get_pending_server_request(request_id=pending["requestId"])
            assert restored is not None
            assert restored["turnId"] is None
            listed = reopened.list_pending_server_requests()
            assert listed[0]["turnId"] is None
        finally:
            reopened.close()


def test_runtime_store_migrates_legacy_pending_requests_turn_id_to_nullable() -> None:
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
        connection = sqlite3.connect(str(db_path))
        try:
            connection.executescript(
                """
                CREATE TABLE session_v2_pending_requests (
                    request_id TEXT PRIMARY KEY,
                    raw_request_id_json TEXT NOT NULL,
                    method TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    item_id TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                INSERT INTO session_v2_pending_requests(
                    request_id,
                    raw_request_id_json,
                    method,
                    thread_id,
                    turn_id,
                    item_id,
                    status,
                    payload_json
                ) VALUES (
                    'req-legacy',
                    '\"legacy-raw\"',
                    'mcpServer/elicitation/request',
                    'thread-1',
                    '',
                    NULL,
                    'pending',
                    '{}'
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

        store = RuntimeStoreV2(db_path=db_path)
        try:
            restored = store.get_pending_server_request(request_id="req-legacy")
            assert restored is not None
            assert restored["turnId"] is None
        finally:
            store.close()


def test_runtime_store_legacy_migration_marker_is_idempotent_and_persisted() -> None:
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
        store = RuntimeStoreV2(db_path=db_path)
        marker = store.mark_legacy_thread_migrated(
            thread_id="thread-legacy-1",
            source_project_id="project-1",
            source_node_id="node-1",
            source_role="execution",
            source_snapshot_version=7,
            source_item_count=12,
            source_pending_request_count=1,
            source_hash="sha256:test",
        )
        assert marker["threadId"] == "thread-legacy-1"
        assert store.has_legacy_migration_marker(thread_id="thread-legacy-1") is True

        duplicate = store.mark_legacy_thread_migrated(thread_id="thread-legacy-1")
        assert duplicate == marker
        store.close()

        reopened = RuntimeStoreV2(db_path=db_path)
        try:
            assert reopened.has_legacy_migration_marker(thread_id="thread-legacy-1") is True
            restored = reopened.read_legacy_migration_marker(thread_id="thread-legacy-1")
            assert restored is not None
            assert restored["sourceProjectId"] == "project-1"
            assert restored["sourceNodeId"] == "node-1"
            assert restored["sourceRole"] == "execution"
            assert restored["sourceItemCount"] == 12
        finally:
            reopened.close()
