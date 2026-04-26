from __future__ import annotations

import uuid
from typing import Any

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol.client import SessionProtocolClientV2
from backend.session_core_v2.transport.stdio_jsonrpc import StdioJsonRpcTransportV2


def ensure_session_core_v2_protocol_compatible(
    *,
    codex_cmd: str | None,
    timeout_sec: int = 12,
) -> None:
    """Fail fast when Codex app-server is below required Session V2 protocol level."""
    transport = StdioJsonRpcTransportV2(
        codex_cmd=codex_cmd,
        default_timeout_sec=max(1, int(timeout_sec)),
        server_request_queue_capacity=1,
    )
    protocol = SessionProtocolClientV2(transport)
    probe_thread_id: str | None = None
    probe_turn_id: str | None = None
    try:
        protocol.initialize(
            {
                "protocolVersion": "2",
                "clientInfo": {
                    "name": "planningtree-session-v2-gate",
                    "version": "1",
                },
            }
        )

        # This catches gross protocol mismatches quickly before probing turns surface.
        protocol.thread_loaded_list({})

        probe_thread_id = _extract_thread_id(protocol.thread_start({"ephemeral": True})) or f"probe-{uuid.uuid4()}"
        try:
            protocol.thread_turns_list(
                probe_thread_id,
                {
                    "limit": 1,
                },
            )
        except SessionCoreError as exc:
            if is_thread_turns_list_unsupported_error(exc):
                raise _required_method_error(
                    codex_cmd=codex_cmd,
                    method="thread/turns/list",
                    message=(
                        "Codex binary is below required protocol level: missing method "
                        "'thread/turns/list'. Set PLANNINGTREE_CODEX_CMD to a compatible Codex binary."
                    ),
                    error=exc,
                ) from exc
            raise _required_method_error(
                codex_cmd=codex_cmd,
                method="thread/turns/list",
                message="Session Core V2 compatibility probe failed while invoking 'thread/turns/list'.",
                error=exc,
            ) from exc

        try:
            turn_start_response = protocol.turn_start(
                probe_thread_id,
                {
                    "clientActionId": f"protocol-gate-start-{uuid.uuid4()}",
                    "input": [
                        {
                            "type": "text",
                            "text": "session-core-v2-protocol-probe",
                        }
                    ],
                },
            )
        except SessionCoreError as exc:
            raise _required_method_error(
                codex_cmd=codex_cmd,
                method="turn/start",
                message="Session Core V2 compatibility probe failed while invoking 'turn/start'.",
                error=exc,
            ) from exc

        probe_turn_id = _extract_turn_id(turn_start_response)
        if not probe_turn_id:
            raise SessionCoreError(
                code="ERR_SESSION_PROTOCOL_MISMATCH",
                message=(
                    "Codex binary is below required protocol level: 'turn/start' must return turnId "
                    "in the accepted response payload."
                ),
                status_code=503,
                details={
                    "codexCmd": codex_cmd,
                    "requiredMethod": "turn/start",
                    "requiredField": "turnId",
                },
            )
    finally:
        if probe_thread_id and probe_turn_id:
            try:
                protocol.turn_interrupt(probe_thread_id, probe_turn_id)
            except Exception:
                pass
        if probe_thread_id:
            try:
                protocol.thread_unsubscribe(probe_thread_id)
            except Exception:
                pass
        transport.stop()


def is_thread_turns_list_unsupported_error(error: SessionCoreError) -> bool:
    if error.code != "ERR_PROVIDER_UNAVAILABLE":
        return False
    details: dict[str, Any] = error.details if isinstance(error.details, dict) else {}
    rpc_code = details.get("rpcCode")
    if rpc_code not in {-32600, -32601}:
        return False
    message = str(error.message or "").lower()
    if "thread/turns/list" not in message:
        return False
    return "unknown variant" in message or "method not found" in message


def _required_method_error(
    *,
    codex_cmd: str | None,
    method: str,
    message: str,
    error: SessionCoreError,
) -> SessionCoreError:
    return SessionCoreError(
        code="ERR_SESSION_PROTOCOL_MISMATCH",
        message=message,
        status_code=503,
        details={
            "codexCmd": codex_cmd,
            "requiredMethod": method,
            "rpcCode": error.details.get("rpcCode") if isinstance(error.details, dict) else None,
            "rpcMessage": error.message,
        },
    )


def _extract_thread_id(response: dict[str, Any]) -> str | None:
    if not isinstance(response, dict):
        return None
    thread = response.get("thread")
    if isinstance(thread, dict):
        value = thread.get("id") or thread.get("threadId")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = response.get("threadId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_turn_id(response: dict[str, Any]) -> str | None:
    if not isinstance(response, dict):
        return None
    turn = response.get("turn")
    if isinstance(turn, dict):
        value = turn.get("id") or turn.get("turnId")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = response.get("turnId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
