from __future__ import annotations

import time
from typing import Any

from backend.session_core_v2.errors import SessionCoreError
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

    def thread_fork(self, *, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_fork(thread_id, params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/fork", extra={"latency_ms": elapsed_ms})
        return self._normalize_thread_config_response(response)

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

    def thread_turns_list(self, *, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        normalized_params = params or {}
        try:
            response = self._protocol_client.thread_turns_list(thread_id, normalized_params)
        except SessionCoreError as exc:
            if not self._is_turns_list_unsupported(exc):
                raise
            response = self._thread_turns_list_fallback(thread_id=thread_id, params=normalized_params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/turns/list", extra={"latency_ms": elapsed_ms})
        data = response.get("data")
        if not isinstance(data, list):
            data = []
        normalized = [self._normalize_turn(turn) for turn in data if isinstance(turn, dict)]
        return {
            "data": normalized,
            "nextCursor": response.get("nextCursor"),
        }

    def _thread_turns_list_fallback(self, *, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        read_response = self._protocol_client.thread_read(thread_id, include_turns=True)
        thread = read_response.get("thread")
        turns = thread.get("turns") if isinstance(thread, dict) else None
        if not isinstance(turns, list):
            turns = []
        cursor_value = self._parse_cursor(params.get("cursor"))
        limit = self._parse_limit(params.get("limit"), default=200)
        if cursor_value >= len(turns):
            page: list[dict[str, Any]] = []
            next_cursor: str | None = None
        else:
            page = [entry for entry in turns[cursor_value : cursor_value + limit] if isinstance(entry, dict)]
            next_offset = cursor_value + len(page)
            next_cursor = str(next_offset) if next_offset < len(turns) else None
        self._logger.info(
            "session_core_v2 thread/turns/list fallback via thread/read",
            extra={"threadId": thread_id, "cursor": cursor_value, "limit": limit},
        )
        return {
            "data": page,
            "nextCursor": next_cursor,
        }

    def thread_loaded_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_loaded_list(params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/loaded/list", extra={"latency_ms": elapsed_ms})
        data = response.get("data")
        if not isinstance(data, list):
            data = []
        normalized = [str(entry).strip() for entry in data if str(entry).strip()]
        return {
            "data": normalized,
            "nextCursor": response.get("nextCursor"),
        }

    def thread_unsubscribe(self, *, thread_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        response = self._protocol_client.thread_unsubscribe(thread_id)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/unsubscribe", extra={"latency_ms": elapsed_ms})
        status = str(response.get("status") or "").strip() or "unsubscribed"
        if status not in {"notLoaded", "notSubscribed", "unsubscribed"}:
            status = "unsubscribed"
        return {"status": status}

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

    @staticmethod
    def _parse_cursor(raw_value: Any) -> int:
        if raw_value is None:
            return 0
        try:
            parsed = int(str(raw_value).strip())
        except Exception:
            return 0
        if parsed < 0:
            return 0
        return parsed

    @staticmethod
    def _parse_limit(raw_value: Any, *, default: int) -> int:
        if raw_value is None:
            return default
        try:
            parsed = int(str(raw_value).strip())
        except Exception:
            return default
        if parsed <= 0:
            return default
        return parsed

    @staticmethod
    def _is_turns_list_unsupported(error: SessionCoreError) -> bool:
        if error.code != "ERR_PROVIDER_UNAVAILABLE":
            return False
        rpc_code = error.details.get("rpcCode") if isinstance(error.details, dict) else None
        if rpc_code not in {-32600, -32601}:
            return False
        message = str(error.message or "").lower()
        return "thread/turns/list" in message and (
            "unknown variant" in message or "method not found" in message
        )

    @staticmethod
    def _normalize_turn(value: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(value)
        normalized.setdefault("id", "")
        status = str(normalized.get("status") or "failed")
        if status not in {"inProgress", "completed", "failed", "interrupted"}:
            status = "failed"
        normalized["status"] = status
        items = normalized.get("items")
        if not isinstance(items, list):
            normalized["items"] = []
        return normalized
