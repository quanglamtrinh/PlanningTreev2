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

        probe_thread_id = f"probe-{uuid.uuid4()}"
        try:
            protocol.thread_turns_list(
                probe_thread_id,
                {
                    "limit": 1,
                },
            )
        except SessionCoreError as exc:
            if not is_thread_turns_list_unsupported_error(exc):
                return
            raise SessionCoreError(
                code="ERR_SESSION_PROTOCOL_MISMATCH",
                message=(
                    "Codex binary is below required protocol level: missing method "
                    "'thread/turns/list'. Set PLANNINGTREE_CODEX_CMD to a compatible Codex binary."
                ),
                status_code=503,
                details={
                    "codexCmd": codex_cmd,
                    "requiredMethod": "thread/turns/list",
                    "rpcCode": exc.details.get("rpcCode") if isinstance(exc.details, dict) else None,
                    "rpcMessage": exc.message,
                },
            ) from exc
    finally:
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

