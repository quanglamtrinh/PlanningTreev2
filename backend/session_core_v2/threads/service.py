from __future__ import annotations

import time
from typing import Any

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol.client import SessionProtocolClientV2
from backend.session_core_v2.protocol.compat_gate import is_thread_turns_list_unsupported_error
from backend.session_core_v2.thread_store import paginate_turns


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
            if not is_thread_turns_list_unsupported_error(exc):
                raise
            read_response = self.thread_read(thread_id=thread_id, include_turns=True)
            thread = read_response.get("thread")
            turns = thread.get("turns") if isinstance(thread, dict) else []
            normalized_turns = (
                [self._normalize_turn(turn) for turn in turns if isinstance(turn, dict)]
                if isinstance(turns, list)
                else []
            )
            cursor = str(normalized_params.get("cursor") or "").strip()
            if cursor.isdigit():
                limit = 50 if normalized_params.get("limit") is None else max(0, int(normalized_params.get("limit")))
                start = int(cursor)
                page = normalized_turns[start : start + limit]
                next_cursor = str(start + limit) if start + limit < len(normalized_turns) and page else None
                return {"data": page, "nextCursor": next_cursor}
            return paginate_turns(
                normalized_turns,
                cursor=cursor or None,
                limit=normalized_params.get("limit"),
                sort_direction=str(normalized_params.get("sortDirection") or "asc"),
            )
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

    def thread_inject_items(self, *, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        self._protocol_client.thread_inject_items(thread_id, params)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._logger.info("session_core_v2 thread/inject_items", extra={"latency_ms": elapsed_ms})
        return {}

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
