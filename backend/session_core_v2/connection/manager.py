from __future__ import annotations

import logging
import time
from typing import Any

from backend.session_core_v2.connection.state_machine import ConnectionStateMachine
from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol.client import SessionProtocolClientV2
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.session_core_v2.threads.service import ThreadServiceV2

logger = logging.getLogger(__name__)

_THREAD_LEVEL_NOTIFICATION_METHODS: set[str] = {
    "thread/started",
    "thread/status/changed",
    "thread/closed",
    "error",
}


class SessionManagerV2:
    def __init__(
        self,
        *,
        protocol_client: SessionProtocolClientV2,
        runtime_store: RuntimeStoreV2,
        connection_state_machine: ConnectionStateMachine,
    ) -> None:
        self._protocol_client = protocol_client
        self._runtime_store = runtime_store
        self._connection_state_machine = connection_state_machine
        self._thread_service = ThreadServiceV2(protocol_client, logger=logger)
        self._protocol_client.set_notification_handler(self._on_notification)

    def initialize(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        phase = self._connection_state_machine.phase
        if phase == "initialized":
            return self.status()

        started = time.perf_counter()
        client_info = request_payload.get("clientInfo")
        client_name = client_info.get("name") if isinstance(client_info, dict) else None
        try:
            self._connection_state_machine.set_connecting()
            response = self._protocol_client.initialize(request_payload)
            server_info = response.get("serverInfo")
            server_version = server_info.get("version") if isinstance(server_info, dict) else None
            self._connection_state_machine.set_initialized(
                client_name=str(client_name or ""),
                server_version=str(server_version or ""),
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("session_core_v2 initialize ok", extra={"latency_ms": elapsed_ms})
            return self.status()
        except SessionCoreError as exc:
            self._connection_state_machine.set_error(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "session_core_v2 initialize failed",
                extra={"latency_ms": elapsed_ms, "error_code": exc.code},
            )
            raise
        except Exception as exc:
            self._connection_state_machine.set_error(
                code="ERR_INTERNAL",
                message="Unexpected initialization failure.",
                details={"reason": str(exc)},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "session_core_v2 initialize unexpected failure",
                extra={"latency_ms": elapsed_ms},
            )
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="Unexpected initialization failure.",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc

    def status(self) -> dict[str, Any]:
        return {"connection": self._connection_state_machine.snapshot()}

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_start(payload)

    def thread_resume(self, *, thread_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_resume(thread_id=thread_id, params=payload)

    def thread_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_list(payload)

    def thread_read(self, *, thread_id: str, include_turns: bool) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_read(thread_id=thread_id, include_turns=include_turns)

    def _ensure_initialized(self) -> None:
        if self._connection_state_machine.phase != "initialized":
            raise SessionCoreError(
                code="ERR_SESSION_NOT_INITIALIZED",
                message="Session has not completed initialize/initialized handshake.",
                status_code=409,
                details={},
            )

    def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        if method not in _THREAD_LEVEL_NOTIFICATION_METHODS:
            return
        thread_id = self._extract_thread_id(params)
        if not thread_id:
            return
        self._runtime_store.append_thread_event(thread_id=thread_id, method=method, params=params)

    @staticmethod
    def _extract_thread_id(params: dict[str, Any]) -> str:
        value = params.get("threadId")
        if isinstance(value, str) and value.strip():
            return value.strip()
        nested_thread = params.get("thread")
        if isinstance(nested_thread, dict):
            nested_id = nested_thread.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                return nested_id.strip()
        return ""

