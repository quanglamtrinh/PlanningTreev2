from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class RuntimeStoreV2:
    """Authoritative runtime store for Session Core V2 (Phase 1 in-memory baseline)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread_sequences: dict[str, int] = defaultdict(int)
        self._journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._snapshot_versions: dict[str, int] = defaultdict(int)

    def append_thread_event(self, *, thread_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return {}
        with self._lock:
            next_seq = self._thread_sequences[normalized_thread_id] + 1
            self._thread_sequences[normalized_thread_id] = next_seq
            event = {
                "schemaVersion": 1,
                "eventId": f"{normalized_thread_id}:{next_seq}",
                "eventSeq": next_seq,
                "tier": "tier0",
                "method": method,
                "threadId": normalized_thread_id,
                "turnId": None,
                "occurredAtMs": int(time.time() * 1000),
                "replayable": True,
                "snapshotVersion": self._snapshot_versions.get(normalized_thread_id) or None,
                "source": "journal",
                "params": params,
            }
            self._journal[normalized_thread_id].append(event)
            return event

    def bump_snapshot(self, thread_id: str) -> int:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return 0
        with self._lock:
            self._snapshot_versions[normalized_thread_id] += 1
            return self._snapshot_versions[normalized_thread_id]

    def read_thread_journal(self, thread_id: str) -> list[dict[str, Any]]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return []
        with self._lock:
            return list(self._journal.get(normalized_thread_id, []))

