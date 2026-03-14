from __future__ import annotations

import threading

from backend.storage.project_ids import normalize_project_id


class ProjectLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, threading.RLock] = {}
        self._lock = threading.Lock()

    def for_project(self, project_id: str) -> threading.RLock:
        normalized = normalize_project_id(project_id)
        with self._lock:
            lock = self._locks.get(normalized)
            if lock is None:
                lock = threading.RLock()
                self._locks[normalized] = lock
            return lock
