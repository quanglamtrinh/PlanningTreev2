from __future__ import annotations

import pytest

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol import compat_gate


def test_is_thread_turns_list_unsupported_error_detects_unknown_variant() -> None:
    error = SessionCoreError(
        code="ERR_PROVIDER_UNAVAILABLE",
        message="Invalid request: unknown variant `thread/turns/list`",
        status_code=502,
        details={"rpcCode": -32600},
    )
    assert compat_gate.is_thread_turns_list_unsupported_error(error) is True


def test_is_thread_turns_list_unsupported_error_ignores_other_errors() -> None:
    error = SessionCoreError(
        code="ERR_PROVIDER_UNAVAILABLE",
        message="thread/turns/list failed: not materialized",
        status_code=502,
        details={"rpcCode": -32000},
    )
    assert compat_gate.is_thread_turns_list_unsupported_error(error) is False


def test_protocol_gate_raises_protocol_mismatch_for_missing_turns_list(monkeypatch) -> None:
    transport_created: list[object] = []

    class FakeTransport:
        def __init__(self, **_: object) -> None:
            self.stopped = False
            transport_created.append(self)

        def stop(self) -> None:
            self.stopped = True

    class FakeProtocol:
        def __init__(self, _: object) -> None:
            pass

        def initialize(self, _: dict[str, object]) -> dict[str, object]:
            return {}

        def thread_loaded_list(self, _: dict[str, object]) -> dict[str, object]:
            return {"data": []}

        def thread_turns_list(self, _thread_id: str, _params: dict[str, object]) -> dict[str, object]:
            raise SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message="unknown variant `thread/turns/list`",
                status_code=502,
                details={"rpcCode": -32600},
            )

    monkeypatch.setattr(compat_gate, "StdioJsonRpcTransportV2", FakeTransport)
    monkeypatch.setattr(compat_gate, "SessionProtocolClientV2", FakeProtocol)

    with pytest.raises(SessionCoreError) as exc_info:
        compat_gate.ensure_session_core_v2_protocol_compatible(codex_cmd="codex", timeout_sec=5)

    assert exc_info.value.code == "ERR_SESSION_PROTOCOL_MISMATCH"
    assert transport_created
    assert getattr(transport_created[0], "stopped") is True
