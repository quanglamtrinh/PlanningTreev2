from __future__ import annotations

from typing import Any

from backend.session_core_v2.transport.stdio_jsonrpc import (
    NotificationHandler,
    ServerRequestHandler,
    StdioJsonRpcTransportV2,
)


class SessionProtocolClientV2:
    """Thin facade around Codex JSON-RPC methods used by Session Core V2."""

    def __init__(self, transport: StdioJsonRpcTransportV2) -> None:
        self._transport = transport

    def set_notification_handler(self, handler: NotificationHandler) -> None:
        self._transport.set_notification_handler(handler)

    def set_server_request_handler(self, handler: ServerRequestHandler) -> None:
        self._transport.set_server_request_handler(handler)

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        response = self._transport.request("initialize", params)
        self._transport.notify("initialized", {})
        return response

    def thread_start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._transport.request("thread/start", params or {})

    def thread_resume(self, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params or {})
        return self._transport.request("thread/resume", payload)

    def thread_fork(self, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params or {})
        return self._transport.request("thread/fork", payload)

    def thread_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._transport.request("thread/list", params or {})

    def thread_read(self, thread_id: str, include_turns: bool) -> dict[str, Any]:
        return self._transport.request(
            "thread/read",
            {"threadId": thread_id, "includeTurns": bool(include_turns)},
        )

    def thread_turns_list(self, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params or {})
        return self._transport.request("thread/turns/list", payload)

    def thread_loaded_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._transport.request("thread/loaded/list", params or {})

    def thread_unsubscribe(self, thread_id: str) -> dict[str, Any]:
        return self._transport.request("thread/unsubscribe", {"threadId": thread_id})

    def turn_start(self, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params)
        return self._transport.request("turn/start", payload)

    def turn_steer(self, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params)
        return self._transport.request("turn/steer", payload)

    def turn_interrupt(self, thread_id: str, turn_id: str) -> dict[str, Any]:
        payload = {"threadId": thread_id, "turnId": turn_id}
        return self._transport.request("turn/interrupt", payload)

    def respond_to_server_request(self, raw_request_id: Any, result: dict[str, Any] | None = None) -> None:
        self._transport.respond_to_server_request(raw_request_id, result)

    def fail_server_request(self, raw_request_id: Any, error: dict[str, Any] | None = None) -> None:
        self._transport.fail_server_request(raw_request_id, error)
