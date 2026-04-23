from __future__ import annotations

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2


def test_turn_state_machine_happy_path_and_terminal_invariants() -> None:
    store = RuntimeStoreV2()
    turn = store.create_turn(thread_id="thread-1", turn_id="turn-1", status="idle")
    assert turn["status"] == "idle"

    running = store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="inProgress")
    assert running["status"] == "inProgress"
    assert store.get_active_turn(thread_id="thread-1")["id"] == "turn-1"

    waiting = store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="waitingUserInput")
    assert waiting["status"] == "waitingUserInput"

    resumed = store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="inProgress")
    assert resumed["status"] == "inProgress"

    completed = store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="completed")
    assert completed["status"] == "completed"
    assert completed["completedAtMs"] is not None
    assert store.get_active_turn(thread_id="thread-1") is None

    with pytest.raises(SessionCoreError) as terminal_exc:
        store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="inProgress")
    assert terminal_exc.value.code == "ERR_TURN_TERMINAL"


def test_turn_state_machine_rejects_illegal_transition() -> None:
    store = RuntimeStoreV2()
    store.create_turn(thread_id="thread-1", turn_id="turn-1", status="idle")

    with pytest.raises(SessionCoreError) as exc_info:
        store.transition_turn(thread_id="thread-1", turn_id="turn-1", next_status="waitingUserInput")
    assert exc_info.value.code == "ERR_TURN_NOT_STEERABLE"
