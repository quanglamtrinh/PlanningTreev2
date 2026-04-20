from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2


def test_idempotency_duplicate_same_payload_returns_previous_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = RuntimeStoreV2(db_path=Path(tmp) / "session_v2.sqlite3")
        payload = {"threadId": "thread-1", "clientActionId": "start-1", "input": [{"type": "text", "text": "hi"}]}
        response = {"turn": {"id": "turn-1", "status": "inProgress", "items": [], "error": None}}
        store.record_idempotent_result(
            action_type="turn/start",
            key="start-1",
            payload=payload,
            response=response,
            thread_id="thread-1",
            turn_id="turn-1",
        )

        resolved = store.resolve_idempotent_result(action_type="turn/start", key="start-1", payload=payload)
        assert resolved == response
        store.close()


def test_idempotency_payload_mismatch_returns_deterministic_error() -> None:
    store = RuntimeStoreV2()
    payload = {"threadId": "thread-1", "clientActionId": "start-1", "input": [{"type": "text", "text": "hi"}]}
    response = {"turn": {"id": "turn-1", "status": "inProgress", "items": [], "error": None}}
    store.record_idempotent_result(
        action_type="turn/start",
        key="start-1",
        payload=payload,
        response=response,
        thread_id="thread-1",
        turn_id="turn-1",
    )

    mismatched = {"threadId": "thread-1", "clientActionId": "start-1", "input": [{"type": "text", "text": "different"}]}
    with pytest.raises(SessionCoreError) as exc_info:
        store.resolve_idempotent_result(action_type="turn/start", key="start-1", payload=mismatched)
    assert exc_info.value.code == "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_idempotency_persists_across_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "session_v2.sqlite3"
        payload = {"threadId": "thread-1", "clientActionId": "start-1", "input": [{"type": "text", "text": "hi"}]}
        response = {"turn": {"id": "turn-1", "status": "inProgress", "items": [], "error": None}}

        store = RuntimeStoreV2(db_path=db_path)
        store.record_idempotent_result(
            action_type="turn/start",
            key="start-1",
            payload=payload,
            response=response,
            thread_id="thread-1",
            turn_id="turn-1",
        )
        store.close()

        reopened = RuntimeStoreV2(db_path=db_path)
        try:
            resolved = reopened.resolve_idempotent_result(
                action_type="turn/start",
                key="start-1",
                payload=payload,
            )
            assert resolved == response
        finally:
            reopened.close()
