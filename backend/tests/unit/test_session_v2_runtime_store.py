from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2

_DAY_MS = 24 * 60 * 60 * 1000


def test_runtime_store_event_replay_and_cursor_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "session_v2.sqlite3"
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
