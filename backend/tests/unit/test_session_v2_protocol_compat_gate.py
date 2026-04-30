from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.routes import session_v4
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

        def thread_start(self, _: dict[str, object]) -> dict[str, object]:
            return {"thread": {"id": "thread-probe"}}

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


def test_protocol_gate_raises_protocol_mismatch_when_turn_start_missing_turn_id(monkeypatch) -> None:
    class FakeTransport:
        def __init__(self, **_: object) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    class FakeProtocol:
        def __init__(self, _: object) -> None:
            pass

        def initialize(self, _: dict[str, object]) -> dict[str, object]:
            return {}

        def thread_loaded_list(self, _: dict[str, object]) -> dict[str, object]:
            return {"data": []}

        def thread_start(self, _: dict[str, object]) -> dict[str, object]:
            return {"thread": {"id": "thread-probe"}}

        def thread_turns_list(self, _thread_id: str, _params: dict[str, object]) -> dict[str, object]:
            return {"data": [], "nextCursor": None}

        def turn_start(self, _thread_id: str, _params: dict[str, object]) -> dict[str, object]:
            return {"accepted": True}

    monkeypatch.setattr(compat_gate, "StdioJsonRpcTransportV2", FakeTransport)
    monkeypatch.setattr(compat_gate, "SessionProtocolClientV2", FakeProtocol)

    with pytest.raises(SessionCoreError) as exc_info:
        compat_gate.ensure_session_core_v2_protocol_compatible(codex_cmd="codex", timeout_sec=5)

    assert exc_info.value.code == "ERR_SESSION_PROTOCOL_MISMATCH"
    assert exc_info.value.details.get("requiredMethod") == "turn/start"
    assert exc_info.value.details.get("requiredField") == "turnId"


def test_session_runtime_request_models_reject_workflow_only_fields() -> None:
    planningtree_only_fields = {
        "projectId": "project-1",
        "nodeId": "node-1",
        "role": "execution",
        "idempotencyKey": "workflow-only",
    }
    cases = [
        (session_v4.ThreadStartRequest, {}),
        (session_v4.ThreadResumeRequest, {}),
        (session_v4.ThreadForkRequest, {}),
        (session_v4.TurnStartRequest, {"input": [{"type": "text", "text": "hello"}]}),
        (
            session_v4.TurnSteerRequest,
            {"expectedTurnId": "turn-1", "input": [{"type": "text", "text": "continue"}]},
        ),
        (session_v4.TurnInterruptRequest, {}),
        (session_v4.InjectItemsRequest, {"items": [{"type": "message", "role": "developer"}]}),
    ]

    for model, base_payload in cases:
        with pytest.raises(ValidationError):
            model.model_validate({**base_payload, **planningtree_only_fields})


def test_thread_recover_request_is_not_exposed() -> None:
    assert not hasattr(session_v4, "ThreadRecoverRequest")
