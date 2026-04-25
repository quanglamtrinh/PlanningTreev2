from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from backend.session_core_v2.thread_store.models import ThreadMetadata, ThreadStatus


class ThreadMetadataStore:
    def __init__(self, *, db_path: str | Path, rollout_root: str | Path) -> None:
        self._db_path = Path(db_path).expanduser().resolve()
        self._rollout_root = Path(rollout_root).expanduser().resolve()
        self._lock = threading.RLock()
        self._rollout_root.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_db()

    @property
    def rollout_root(self) -> Path:
        return self._rollout_root

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_or_update(
        self,
        *,
        thread_id: str,
        project_id: str | None = None,
        title: str | None = None,
        status: ThreadStatus = "notLoaded",
        native_session_id: str | None = None,
        forked_from_id: str | None = None,
        archived_at_ms: int | None = None,
        rollout_path: str | None = None,
        now_ms: int | None = None,
    ) -> ThreadMetadata:
        normalized_thread_id = self._normalize_non_empty(thread_id, "thread_id")
        timestamp_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        resolved_path = str(Path(rollout_path).expanduser().resolve()) if rollout_path else str(self.default_rollout_path(normalized_thread_id))
        with self._lock:
            existing = self.get(normalized_thread_id)
            created_at_ms = existing.created_at_ms if existing else timestamp_ms
            merged = ThreadMetadata(
                thread_id=normalized_thread_id,
                project_id=project_id if project_id is not None else (existing.project_id if existing else None),
                title=title if title is not None else (existing.title if existing else None),
                created_at_ms=created_at_ms,
                updated_at_ms=max(timestamp_ms, existing.updated_at_ms if existing else timestamp_ms),
                status=status or (existing.status if existing else "notLoaded"),
                rollout_path=resolved_path,
                native_session_id=native_session_id if native_session_id is not None else (existing.native_session_id if existing else None),
                forked_from_id=forked_from_id if forked_from_id is not None else (existing.forked_from_id if existing else None),
                archived_at_ms=archived_at_ms if archived_at_ms is not None else (existing.archived_at_ms if existing else None),
            )
            self._upsert_locked(merged)
            return merged

    def get(self, thread_id: str) -> ThreadMetadata | None:
        normalized_thread_id = self._normalize_non_empty(thread_id, "thread_id")
        with self._lock:
            row = self._db.execute(
                """
                SELECT thread_id, project_id, title, created_at_ms, updated_at_ms, status,
                       rollout_path, native_session_id, forked_from_id, archived_at_ms
                FROM session_threads
                WHERE thread_id = ?
                """,
                (normalized_thread_id,),
            ).fetchone()
        return self._row_to_metadata(row) if row is not None else None

    def list(self, *, include_archived: bool = False, limit: int | None = None) -> list[ThreadMetadata]:
        clauses = []
        params: list[Any] = []
        if not include_archived:
            clauses.append("archived_at_ms IS NULL")
        sql = (
            "SELECT thread_id, project_id, title, created_at_ms, updated_at_ms, status, "
            "rollout_path, native_session_id, forked_from_id, archived_at_ms FROM session_threads"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at_ms DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(0, int(limit)))
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_metadata(row) for row in rows]

    def mark_archived(self, thread_id: str, *, archived_at_ms: int | None = None) -> ThreadMetadata:
        normalized_thread_id = self._normalize_non_empty(thread_id, "thread_id")
        timestamp_ms = int(archived_at_ms if archived_at_ms is not None else time.time() * 1000)
        with self._lock:
            existing = self.get(normalized_thread_id)
            if existing is None:
                existing = self.create_or_update(thread_id=normalized_thread_id, now_ms=timestamp_ms)
            updated = ThreadMetadata(
                **{
                    **existing.__dict__,
                    "updated_at_ms": timestamp_ms,
                    "archived_at_ms": timestamp_ms,
                }
            )
            self._upsert_locked(updated)
            return updated

    def update_status(self, thread_id: str, status: ThreadStatus, *, now_ms: int | None = None) -> ThreadMetadata:
        normalized_thread_id = self._normalize_non_empty(thread_id, "thread_id")
        timestamp_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        with self._lock:
            existing = self.get(normalized_thread_id)
            if existing is None:
                return self.create_or_update(thread_id=normalized_thread_id, status=status, now_ms=timestamp_ms)
            updated = ThreadMetadata(**{**existing.__dict__, "status": status, "updated_at_ms": timestamp_ms})
            self._upsert_locked(updated)
            return updated

    def update_title(self, thread_id: str, title: str | None, *, now_ms: int | None = None) -> ThreadMetadata:
        normalized_thread_id = self._normalize_non_empty(thread_id, "thread_id")
        timestamp_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        with self._lock:
            existing = self.get(normalized_thread_id)
            if existing is None:
                return self.create_or_update(thread_id=normalized_thread_id, title=title, now_ms=timestamp_ms)
            updated = ThreadMetadata(**{**existing.__dict__, "title": title, "updated_at_ms": timestamp_ms})
            self._upsert_locked(updated)
            return updated

    def default_rollout_path(self, thread_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in thread_id)
        return self._rollout_root / f"{safe}.jsonl"

    def _init_db(self) -> None:
        with self._lock:
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_threads (
                    thread_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    title TEXT,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    rollout_path TEXT NOT NULL,
                    native_session_id TEXT,
                    forked_from_id TEXT,
                    archived_at_ms INTEGER
                )
                """
            )
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_session_threads_updated ON session_threads(updated_at_ms DESC)")
            self._db.commit()

    def _upsert_locked(self, metadata: ThreadMetadata) -> None:
        self._db.execute(
            """
            INSERT INTO session_threads(
                thread_id, project_id, title, created_at_ms, updated_at_ms, status,
                rollout_path, native_session_id, forked_from_id, archived_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                project_id = excluded.project_id,
                title = excluded.title,
                created_at_ms = excluded.created_at_ms,
                updated_at_ms = excluded.updated_at_ms,
                status = excluded.status,
                rollout_path = excluded.rollout_path,
                native_session_id = excluded.native_session_id,
                forked_from_id = excluded.forked_from_id,
                archived_at_ms = excluded.archived_at_ms
            """,
            (
                metadata.thread_id,
                metadata.project_id,
                metadata.title,
                metadata.created_at_ms,
                metadata.updated_at_ms,
                metadata.status,
                metadata.rollout_path,
                metadata.native_session_id,
                metadata.forked_from_id,
                metadata.archived_at_ms,
            ),
        )
        self._db.commit()

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> ThreadMetadata:
        return ThreadMetadata(
            thread_id=str(row["thread_id"]),
            project_id=row["project_id"],
            title=row["title"],
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            status=row["status"],
            rollout_path=str(row["rollout_path"]),
            native_session_id=row["native_session_id"],
            forked_from_id=row["forked_from_id"],
            archived_at_ms=row["archived_at_ms"],
        )

    @staticmethod
    def _normalize_non_empty(value: str, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field_name} is required")
        return normalized
