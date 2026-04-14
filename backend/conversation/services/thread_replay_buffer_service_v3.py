from __future__ import annotations

import copy
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from typing import Callable

_CONTROL_EVENT_TYPES = {"stream_open", "replay_miss"}


@dataclass(frozen=True)
class ReplayBufferReadResultV3:
    replay_miss: bool
    events: tuple[dict[str, Any], ...]
    replay_tail_event_id: int | None


@dataclass(frozen=True)
class _ReplayEntry:
    event_id: int
    inserted_at_ms: int
    envelope: dict[str, Any]


class ThreadReplayBufferServiceV3:
    def __init__(
        self,
        *,
        max_events: int = 500,
        ttl_seconds: int = 15 * 60,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._max_events = max(1, int(max_events))
        self._ttl_ms = max(1_000, int(ttl_seconds) * 1_000)
        self._now_ms = now_ms if callable(now_ms) else lambda: int(time.time() * 1000)
        self._lock = threading.Lock()
        self._buffers: dict[tuple[str, str, str, str], deque[_ReplayEntry]] = {}
        self._evicted_high_water: dict[tuple[str, str, str, str], int] = {}

    @staticmethod
    def _normalize(value: Any) -> str:
        return str(value or "").strip()

    def _to_key(self, project_id: str, node_id: str, thread_role: str, thread_id: str) -> tuple[str, str, str, str]:
        return (
            self._normalize(project_id),
            self._normalize(node_id),
            self._normalize(thread_role),
            self._normalize(thread_id),
        )

    @staticmethod
    def _parse_event_id(envelope: dict[str, Any]) -> int | None:
        event_id = str(envelope.get("event_id") or envelope.get("eventId") or "").strip()
        if not event_id or not event_id.isdigit():
            return None
        return int(event_id)

    @staticmethod
    def _is_control_event(envelope: dict[str, Any]) -> bool:
        event_type = str(envelope.get("event_type") or envelope.get("type") or "").strip()
        return event_type in _CONTROL_EVENT_TYPES

    def _record_evicted(self, key: tuple[str, str, str, str], event_id: int) -> None:
        self._evicted_high_water[key] = max(event_id, int(self._evicted_high_water.get(key) or 0))

    def _evict_locked(self, key: tuple[str, str, str, str], queue: deque[_ReplayEntry], now_ms: int) -> None:
        expires_before = now_ms - self._ttl_ms
        while queue and queue[0].inserted_at_ms < expires_before:
            self._record_evicted(key, queue.popleft().event_id)

        while len(queue) > self._max_events:
            self._record_evicted(key, queue.popleft().event_id)

        if not queue:
            self._buffers.pop(key, None)

    def append_business_event(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: str,
        thread_id: str,
        envelope: dict[str, Any],
    ) -> None:
        if not isinstance(envelope, dict) or self._is_control_event(envelope):
            return
        event_id = self._parse_event_id(envelope)
        if event_id is None:
            return

        key = self._to_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            now = int(self._now_ms())
            queue = self._buffers.setdefault(key, deque())
            self._evict_locked(key, queue, now)
            queue = self._buffers.setdefault(key, deque())
            queue.append(
                _ReplayEntry(
                    event_id=event_id,
                    inserted_at_ms=now,
                    envelope=copy.deepcopy(envelope),
                )
            )
            self._evict_locked(key, queue, now)

    def read_business_events_since(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: str,
        thread_id: str,
        last_event_id: str,
    ) -> ReplayBufferReadResultV3:
        key = self._to_key(project_id, node_id, thread_role, thread_id)
        cursor = int(last_event_id)

        with self._lock:
            now = int(self._now_ms())
            queue = self._buffers.get(key)
            if queue is not None:
                self._evict_locked(key, queue, now)
                queue = self._buffers.get(key)

            evicted_high_water = int(self._evicted_high_water.get(key) or 0)
            if cursor < evicted_high_water:
                return ReplayBufferReadResultV3(
                    replay_miss=True,
                    events=(),
                    replay_tail_event_id=None,
                )

            if not queue:
                return ReplayBufferReadResultV3(
                    replay_miss=False,
                    events=(),
                    replay_tail_event_id=None,
                )

            replay_entries = [entry for entry in queue if entry.event_id > cursor]
            replay_tail = replay_entries[-1].event_id if replay_entries else None
            return ReplayBufferReadResultV3(
                replay_miss=False,
                events=tuple(copy.deepcopy(entry.envelope) for entry in replay_entries),
                replay_tail_event_id=replay_tail,
            )
