from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2


@contextmanager
def _workspace_temp_dir() -> Iterator[Path]:
    root = Path("pytest_tmp_dir") / "session_v2_idempotency" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_idempotency_duplicate_same_payload_returns_previous_result() -> None:
    with _workspace_temp_dir() as tmp:
        store = RuntimeStoreV2(db_path=tmp / "session_v2.sqlite3")
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
    with _workspace_temp_dir() as tmp:
        db_path = tmp / "session_v2.sqlite3"
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


def test_request_resolution_idempotency_duplicate_same_payload_returns_previous_result() -> None:
    store = RuntimeStoreV2()
    payload = {"requestId": "request-1", "result": {"decision": "accept"}}
    response = {"status": "accepted"}
    store.record_idempotent_result(
        action_type="requests/resolve",
        key="resolve-1",
        payload=payload,
        response=response,
        thread_id="thread-1",
        turn_id="turn-1",
        request_id="request-1",
    )

    resolved = store.resolve_idempotent_result(
        action_type="requests/resolve",
        key="resolve-1",
        payload=payload,
    )
    assert resolved == response


def test_request_resolution_idempotency_payload_mismatch_is_deterministic() -> None:
    store = RuntimeStoreV2()
    payload = {"requestId": "request-1", "reason": "decline"}
    response = {"status": "accepted"}
    store.record_idempotent_result(
        action_type="requests/reject",
        key="reject-1",
        payload=payload,
        response=response,
        thread_id="thread-1",
        turn_id="turn-1",
        request_id="request-1",
    )

    with pytest.raises(SessionCoreError) as exc_info:
        store.resolve_idempotent_result(
            action_type="requests/reject",
            key="reject-1",
            payload={"requestId": "request-1", "reason": "different"},
        )
    assert exc_info.value.code == "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH"
