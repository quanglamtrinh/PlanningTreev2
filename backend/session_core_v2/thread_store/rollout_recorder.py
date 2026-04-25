from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.session_core_v2.thread_store.metadata_store import ThreadMetadataStore
from backend.session_core_v2.thread_store.models import (
    RolloutLine,
    ThreadMetadata,
    normalize_rollout_item,
)


class ThreadRolloutRecorder:
    def __init__(self, *, metadata_store: ThreadMetadataStore) -> None:
        self._metadata_store = metadata_store
        self._lock = threading.RLock()

    @property
    def metadata_store(self) -> ThreadMetadataStore:
        return self._metadata_store

    def create(self, metadata: ThreadMetadata) -> ThreadMetadata:
        with self._lock:
            path = Path(metadata.rollout_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        return self._metadata_store.create_or_update(
            thread_id=metadata.thread_id,
            project_id=metadata.project_id,
            title=metadata.title,
            status=metadata.status,
            native_session_id=metadata.native_session_id,
            forked_from_id=metadata.forked_from_id,
            archived_at_ms=metadata.archived_at_ms,
            rollout_path=metadata.rollout_path,
            now_ms=metadata.updated_at_ms,
        )

    def ensure_thread(
        self,
        *,
        thread_id: str,
        project_id: str | None = None,
        title: str | None = None,
        status: str = "running",
        native_session_id: str | None = None,
        forked_from_id: str | None = None,
    ) -> ThreadMetadata:
        metadata = self._metadata_store.create_or_update(
            thread_id=thread_id,
            project_id=project_id,
            title=title,
            status=status,  # type: ignore[arg-type]
            native_session_id=native_session_id,
            forked_from_id=forked_from_id,
        )
        self.create(metadata)
        return metadata

    def append_items(self, thread_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return []
        metadata = self._metadata_store.get(thread_id)
        if metadata is None:
            metadata = self.ensure_thread(thread_id=thread_id)
        normalized_items = [normalize_rollout_item(item) for item in items]
        with self._lock:
            path = Path(metadata.rollout_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            seen_event_ids = self._load_event_ids_locked(path)
            appended: list[dict[str, Any]] = []
            with path.open("a", encoding="utf-8") as handle:
                for item in normalized_items:
                    event_id = self._event_id(item)
                    if event_id and event_id in seen_event_ids:
                        continue
                    if event_id:
                        seen_event_ids.add(event_id)
                    line = {
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                        "item": item,
                    }
                    handle.write(json.dumps(line, ensure_ascii=True, separators=(",", ":")))
                    handle.write("\n")
                    appended.append(item)
                handle.flush()
        return appended

    def load_lines(self, thread_id: str) -> list[RolloutLine]:
        metadata = self._metadata_store.get(thread_id)
        if metadata is None:
            raise FileNotFoundError(f"no rollout found for thread id {thread_id}")
        path = Path(metadata.rollout_path)
        if not path.exists():
            raise FileNotFoundError(f"no rollout found for thread id {thread_id}")
        lines: list[RolloutLine] = []
        with self._lock:
            with path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    payload = json.loads(raw)
                    item = payload.get("item")
                    if not isinstance(item, dict):
                        continue
                    timestamp = str(payload.get("timestamp") or "")
                    lines.append(RolloutLine(timestamp=timestamp, item=item))
        return lines

    def load_items(self, thread_id: str) -> list[dict[str, Any]]:
        return [line.item for line in self.load_lines(thread_id)]

    def rollout_path_for(self, thread_id: str) -> Path:
        metadata = self._metadata_store.get(thread_id)
        if metadata is None:
            return self._metadata_store.default_rollout_path(thread_id)
        return Path(metadata.rollout_path)

    def _load_event_ids_locked(self, path: Path) -> set[str]:
        if not path.exists():
            return set()
        event_ids: set[str] = set()
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                item = payload.get("item")
                if isinstance(item, dict):
                    event_id = self._event_id(item)
                    if event_id:
                        event_ids.add(event_id)
        return event_ids

    @staticmethod
    def _event_id(item: dict[str, Any]) -> str | None:
        direct = item.get("event_id") or item.get("eventId")
        if direct:
            return str(direct)
        event = item.get("event")
        if isinstance(event, dict):
            nested = event.get("event_id") or event.get("eventId")
            if nested:
                return str(nested)
        return None
