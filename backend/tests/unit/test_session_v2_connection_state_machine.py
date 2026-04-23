from __future__ import annotations

import pytest

from backend.session_core_v2.connection.state_machine import ConnectionStateMachine
from backend.session_core_v2.errors import SessionCoreError


def test_connection_state_machine_happy_path() -> None:
    sm = ConnectionStateMachine()
    assert sm.snapshot()["phase"] == "disconnected"

    sm.set_connecting()
    assert sm.snapshot()["phase"] == "connecting"

    sm.set_initialized(client_name="planningtree", server_version="1.0.0")
    assert sm.snapshot()["phase"] == "initialized"
    assert sm.snapshot()["clientName"] == "planningtree"
    assert sm.snapshot()["serverVersion"] == "1.0.0"

    sm.set_error(code="ERR_PROVIDER_UNAVAILABLE", message="upstream failed", details={"x": 1})
    assert sm.snapshot()["phase"] == "error"
    assert sm.snapshot()["error"]["code"] == "ERR_PROVIDER_UNAVAILABLE"

    sm.set_connecting()
    sm.set_initialized(client_name="planningtree", server_version="1.0.1")
    sm.set_disconnected()
    assert sm.snapshot()["phase"] == "disconnected"


def test_connection_state_machine_rejects_illegal_transition() -> None:
    sm = ConnectionStateMachine()
    with pytest.raises(SessionCoreError) as exc_info:
        sm.set_initialized(client_name="x", server_version="y")
    assert exc_info.value.code == "ERR_INTERNAL"
    assert "Illegal connection transition" in exc_info.value.message

