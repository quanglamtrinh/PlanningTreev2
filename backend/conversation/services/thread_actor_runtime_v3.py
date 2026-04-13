from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.conversation.domain.types_v3 import ThreadRoleV3, ThreadSnapshotV3, copy_snapshot_v3


def _normalize(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class _ThreadActorStateV3:
    snapshot: ThreadSnapshotV3
    last_checkpoint_ms: int
    last_journal_seq: int = 0
    dirty_event_start: int | None = None
    dirty_event_end: int | None = None
    dirty_events_count: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)


class ThreadActorRuntimeV3:
    def __init__(self, *, now_ms: Callable[[], int] | None = None) -> None:
        self._now_ms = now_ms if callable(now_ms) else lambda: int(time.monotonic() * 1000)
        self._actors: dict[tuple[str, str, str, str], _ThreadActorStateV3] = {}
        self._lock = threading.Lock()

    @staticmethod
    def actor_key(
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
    ) -> tuple[str, str, str, str]:
        return (_normalize(project_id), _normalize(node_id), _normalize(thread_role), _normalize(thread_id))

    def has_actor(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
    ) -> bool:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            return key in self._actors

    def bootstrap_actor(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
        last_journal_seq: int = 0,
        replace: bool = False,
    ) -> ThreadSnapshotV3:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            state = self._actors.get(key)
            if state is None or replace:
                state = _ThreadActorStateV3(
                    snapshot=copy_snapshot_v3(snapshot),
                    last_checkpoint_ms=int(self._now_ms()),
                    last_journal_seq=max(0, int(last_journal_seq)),
                )
                self._actors[key] = state
            with state.lock:
                return copy_snapshot_v3(state.snapshot)

    def get_actor_snapshot(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
    ) -> ThreadSnapshotV3 | None:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            state = self._actors.get(key)
        if state is None:
            return None
        with state.lock:
            return copy_snapshot_v3(state.snapshot)

    @staticmethod
    def _parse_event_id(envelope: dict[str, Any]) -> int | None:
        raw = str(envelope.get("event_id") or envelope.get("eventId") or "").strip()
        if not raw.isdigit():
            return None
        return int(raw)

    def apply_events(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
        envelopes: list[dict[str, Any]],
    ) -> None:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            state = self._actors.get(key)
            if state is None:
                state = _ThreadActorStateV3(snapshot=copy_snapshot_v3(snapshot), last_checkpoint_ms=int(self._now_ms()))
                self._actors[key] = state
        parsed_ids = [event_id for event_id in (self._parse_event_id(envelope) for envelope in envelopes) if event_id is not None]
        with state.lock:
            state.snapshot = copy_snapshot_v3(snapshot)
            if parsed_ids:
                minimum = min(parsed_ids)
                maximum = max(parsed_ids)
                state.dirty_event_start = minimum if state.dirty_event_start is None else min(state.dirty_event_start, minimum)
                state.dirty_event_end = maximum if state.dirty_event_end is None else max(state.dirty_event_end, maximum)
                state.dirty_events_count += len(parsed_ids)

    def checkpoint_stats(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
    ) -> dict[str, Any]:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            state = self._actors.get(key)
        if state is None:
            return {
                "exists": False,
                "elapsed_ms": 0,
                "dirty_events_count": 0,
                "dirty_event_start": None,
                "dirty_event_end": None,
                "last_journal_seq": 0,
                "snapshot": None,
            }
        with state.lock:
            now_ms = int(self._now_ms())
            return {
                "exists": True,
                "elapsed_ms": max(0, now_ms - int(state.last_checkpoint_ms)),
                "dirty_events_count": int(state.dirty_events_count),
                "dirty_event_start": state.dirty_event_start,
                "dirty_event_end": state.dirty_event_end,
                "last_journal_seq": int(state.last_journal_seq),
                "snapshot": copy_snapshot_v3(state.snapshot),
            }

    def mark_checkpoint_committed(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
        journal_seq: int,
    ) -> None:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            state = self._actors.get(key)
            if state is None:
                state = _ThreadActorStateV3(snapshot=copy_snapshot_v3(snapshot), last_checkpoint_ms=int(self._now_ms()))
                self._actors[key] = state
        with state.lock:
            state.snapshot = copy_snapshot_v3(snapshot)
            state.last_checkpoint_ms = int(self._now_ms())
            state.last_journal_seq = max(int(state.last_journal_seq), int(journal_seq))
            state.dirty_event_start = None
            state.dirty_event_end = None
            state.dirty_events_count = 0

    def evict_actor(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
    ) -> bool:
        key = self.actor_key(project_id, node_id, thread_role, thread_id)
        with self._lock:
            return self._actors.pop(key, None) is not None

    @staticmethod
    def snapshot_signature(snapshot: ThreadSnapshotV3) -> str:
        items = snapshot.get("items", [])
        last_item = items[-1] if items else {}
        signature_payload = {
            "snapshotVersion": int(snapshot.get("snapshotVersion") or 0),
            "processingState": str(snapshot.get("processingState") or ""),
            "activeTurnId": str(snapshot.get("activeTurnId") or ""),
            "itemCount": len(items),
            "lastItemId": str(last_item.get("id") or ""),
            "lastItemStatus": str(last_item.get("status") or ""),
        }
        return json.dumps(signature_payload, ensure_ascii=True, sort_keys=True)

    def compare_actor_snapshot_signature(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        snapshot: ThreadSnapshotV3,
    ) -> bool:
        actor_snapshot = self.get_actor_snapshot(project_id, node_id, thread_role, thread_id)
        if actor_snapshot is None:
            return False
        return self.snapshot_signature(actor_snapshot) == self.snapshot_signature(snapshot)
