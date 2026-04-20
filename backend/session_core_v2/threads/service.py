from __future__ import annotations

import time
from typing import Any

from backend.session_core_v2.protocol.client import SessionProtocolClientV2


def _now_ms() -> int:
    return int(time.time() * 1000)


class ThreadServiceV2:
    def __init__(self, protocol_client: SessionProtocolClientV2, *, logger: Any) -> None:
        self._protocol_client = protocol_client
        self._logger = logger

    def thread_start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_start(params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/start", extra={"latency_ms": elapsed_ms})
        return self._normalize_thread_config_response(response)

    def thread_resume(self, *, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_resume(thread_id, params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/resume", extra={"latency_ms": elapsed_ms})
        return self._normalize_thread_config_response(response, fallback_thread_id=thread_id)

    def thread_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_list(params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/list", extra={"latency_ms": elapsed_ms})
        data = response.get("data")
        if not isinstance(data, list):
            data = []
        normalized = [self._normalize_thread(thread) for thread in data if isinstance(thread, dict)]
        return {
            "data": normalized,
            "nextCursor": response.get("nextCursor"),
        }

    def thread_read(self, *, thread_id: str, include_turns: bool) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_read(thread_id, include_turns=include_turns)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/read", extra={"latency_ms": elapsed_ms})
        thread = response.get("thread")
        if not isinstance(thread, dict):
            thread = {}
        return {"thread": self._normalize_thread(thread, fallback_thread_id=thread_id)}

    def _normalize_thread_config_response(
        self,
        response: dict[str, Any],
        *,
        fallback_thread_id: str | None = None,
    ) -> dict[str, Any]:
        thread = response.get("thread")
        if not isinstance(thread, dict):
            thread = {}
        normalized: dict[str, Any] = {
            "thread": self._normalize_thread(thread, fallback_thread_id=fallback_thread_id),
        }
        for key in (
            "model",
            "modelProvider",
            "cwd",
            "approvalPolicy",
            "sandbox",
            "reasoningEffort",
            "serviceTier",
        ):
            if key in response:
                normalized[key] = response.get(key)
        return normalized

    @staticmethod
    def _normalize_thread(
        value: dict[str, Any],
        *,
        fallback_thread_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = dict(value)
        normalized.setdefault("id", fallback_thread_id or "")
        normalized.setdefault("name", None)
        normalized.setdefault("preview", None)
        normalized.setdefault("path", None)
        normalized.setdefault("cwd", "")
        normalized.setdefault("modelProvider", "unknown")
        status = normalized.get("status")
        if not isinstance(status, dict) or "type" not in status:
            normalized["status"] = {"type": "notLoaded"}
        turns = normalized.get("turns")
        if not isinstance(turns, list):
            normalized["turns"] = []
        normalized.setdefault("createdAt", _now_ms())
        normalized.setdefault("updatedAt", _now_ms())
        return normalized

