from __future__ import annotations

import threading
from typing import Any


class AskRolloutMetricsService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {
            "ask_stream_session_total": 0,
            "ask_stream_reconnect_total": 0,
            "ask_stream_error_total": 0,
            "ask_guard_violation_total": 0,
            "ask_shaping_action_total": 0,
            "ask_shaping_action_failed_total": 0,
        }

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def record_stream_session(self) -> None:
        self._increment("ask_stream_session_total")

    def record_stream_reconnect(self) -> None:
        self._increment("ask_stream_reconnect_total")

    def record_stream_error(self) -> None:
        self._increment("ask_stream_error_total")

    def record_guard_violation(self) -> None:
        self._increment("ask_guard_violation_total")

    def record_shaping_action_started(self) -> None:
        self._increment("ask_shaping_action_total")

    def record_shaping_action_failed(self) -> None:
        self._increment("ask_shaping_action_failed_total")

    def record_frontend_event(self, event: str) -> None:
        normalized = str(event or "").strip().lower()
        if normalized == "stream_reconnect":
            self.record_stream_reconnect()
            return
        if normalized == "stream_error":
            self.record_stream_error()
            return
        raise ValueError(f"Unknown ask rollout metric event: {event!r}.")

    def as_public_payload(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            **snapshot,
            "ask_stream_error_rate": _safe_rate(
                snapshot["ask_stream_error_total"],
                snapshot["ask_stream_session_total"],
            ),
            "ask_shaping_action_failed_rate": _safe_rate(
                snapshot["ask_shaping_action_failed_total"],
                snapshot["ask_shaping_action_total"],
            ),
        }

    def _increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] = int(self._counters.get(key, 0)) + int(amount)


def _safe_rate(numerator: int, denominator: int) -> float:
    if int(denominator) <= 0:
        return 0.0
    return float(numerator) / float(denominator)
