from __future__ import annotations

import time
from typing import Any

from backend.session_core_v2.protocol.client import SessionProtocolClientV2


class TurnServiceV2:
    def __init__(self, protocol_client: SessionProtocolClientV2, *, logger: Any) -> None:
        self._protocol_client = protocol_client
        self._logger = logger

    def turn_start(self, *, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.turn_start(thread_id, params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info(
            "session_core_v2 turn/start",
            extra={"latency_ms": elapsed_ms, "threadId": thread_id, "turnId": None, "eventSeq": None, "errorCode": None},
        )
        return response

    def turn_steer(self, *, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.turn_steer(thread_id, params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info(
            "session_core_v2 turn/steer",
            extra={"latency_ms": elapsed_ms, "threadId": thread_id, "turnId": None, "eventSeq": None, "errorCode": None},
        )
        return response

    def turn_interrupt(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.turn_interrupt(thread_id, turn_id)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info(
            "session_core_v2 turn/interrupt",
            extra={
                "latency_ms": elapsed_ms,
                "threadId": thread_id,
                "turnId": turn_id,
                "eventSeq": None,
                "errorCode": None,
            },
        )
        return response
