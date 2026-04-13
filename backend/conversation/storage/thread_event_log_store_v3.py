from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.conversation.domain.types_v3 import ThreadEventLogRecordV3, ThreadRoleV3
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import ensure_dir, iso_now
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore


class ThreadEventLogStoreV3:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _conversation_dir(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "conversation_v3" / node_id

    def path(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> Path:
        return self._conversation_dir(project_id, node_id) / f"{thread_role}.event_log.jsonl"

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _require_int(payload: dict[str, Any], key: str) -> int:
        raw = payload.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"Thread event-log record requires integer field '{key}'.")
        return int(raw)

    @staticmethod
    def _require_str(payload: dict[str, Any], key: str) -> str:
        raw = str(payload.get(key) or "").strip()
        if not raw:
            raise ValueError(f"Thread event-log record requires string field '{key}'.")
        return raw

    def _normalize_record(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        record: ThreadEventLogRecordV3 | dict[str, Any],
    ) -> ThreadEventLogRecordV3:
        payload = dict(record) if isinstance(record, dict) else {}
        log_seq = self._require_int(payload, "logSeq")
        event_id = self._require_int(payload, "eventId")
        if log_seq <= 0:
            raise ValueError("Thread event-log field 'logSeq' must be > 0.")
        if event_id <= 0:
            raise ValueError("Thread event-log field 'eventId' must be > 0.")
        raw_payload = payload.get("payload")
        if not isinstance(raw_payload, dict):
            raise ValueError("Thread event-log field 'payload' must be an object.")
        snapshot_version = self._require_int(payload, "snapshotVersionAtAppend")
        if snapshot_version < 0:
            raise ValueError("Thread event-log field 'snapshotVersionAtAppend' must be >= 0.")
        created_at = str(payload.get("createdAt") or "").strip() or iso_now()
        return {
            "logSeq": log_seq,
            "projectId": str(project_id or "").strip(),
            "nodeId": str(node_id or "").strip(),
            "threadRole": str(thread_role or "").strip(),
            "threadId": self._require_str(payload, "threadId"),
            "eventId": event_id,
            "snapshotVersionAtAppend": snapshot_version,
            "payload": raw_payload,
            "createdAt": created_at,
        }

    def _read_all_locked(self, project_id: str, node_id: str, thread_role: ThreadRoleV3) -> list[ThreadEventLogRecordV3]:
        target = self.path(project_id, node_id, thread_role)
        if not target.exists():
            return []
        records: list[ThreadEventLogRecordV3] = []
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
                trimmed = line.strip()
                if not trimmed:
                    continue
                payload = json.loads(trimmed)
                if not isinstance(payload, dict):
                    raise ValueError("Thread event-log line must decode to JSON object.")
                records.append(self._normalize_record(project_id, node_id, thread_role, payload))
        records.sort(key=lambda item: int(item.get("logSeq") or 0))
        return records

    def append_event_record(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        record: ThreadEventLogRecordV3 | dict[str, Any],
    ) -> ThreadEventLogRecordV3:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_record(project_id, node_id, thread_role, record)
            target = self.path(project_id, node_id, thread_role)
            ensure_dir(target.parent)
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(normalized, ensure_ascii=True))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            return normalized

    def read_tail_after_log_seq(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str,
        cursor: int,
    ) -> list[ThreadEventLogRecordV3]:
        with self._lock_registry.for_project(project_id):
            normalized_thread_id = str(thread_id or "").strip()
            if not normalized_thread_id:
                return []
            cursor_value = max(0, int(cursor))
            return [
                record
                for record in self._read_all_locked(project_id, node_id, thread_role)
                if str(record.get("threadId") or "").strip() == normalized_thread_id
                and int(record.get("logSeq") or 0) > cursor_value
            ]

    def read_tail_after_snapshot_version(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str,
        snapshot_version: int,
    ) -> list[ThreadEventLogRecordV3]:
        with self._lock_registry.for_project(project_id):
            normalized_thread_id = str(thread_id or "").strip()
            if not normalized_thread_id:
                return []
            snapshot_cursor = max(0, int(snapshot_version))
            return [
                record
                for record in self._read_all_locked(project_id, node_id, thread_role)
                if str(record.get("threadId") or "").strip() == normalized_thread_id
                and int(record.get("snapshotVersionAtAppend") or 0) > snapshot_cursor
            ]

    def latest_log_seq(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str,
    ) -> int:
        records = self.read_tail_after_log_seq(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
            cursor=0,
        )
        if not records:
            return 0
        return int(records[-1].get("logSeq") or 0)

    def count_entries(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str,
    ) -> int:
        records = self.read_tail_after_log_seq(
            project_id,
            node_id,
            thread_role,
            thread_id=thread_id,
            cursor=0,
        )
        return len(records)

    def prune_before_event_id(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        *,
        thread_id: str,
        event_id: int,
    ) -> int:
        with self._lock_registry.for_project(project_id):
            target = self.path(project_id, node_id, thread_role)
            if not target.exists():
                return 0
            normalized_thread_id = str(thread_id or "").strip()
            if not normalized_thread_id:
                return 0
            prune_cursor = max(0, int(event_id))
            all_records = self._read_all_locked(project_id, node_id, thread_role)
            keep_records: list[ThreadEventLogRecordV3] = []
            removed = 0
            for record in all_records:
                same_thread = str(record.get("threadId") or "").strip() == normalized_thread_id
                current_event_id = int(record.get("eventId") or 0)
                if same_thread and current_event_id <= prune_cursor:
                    removed += 1
                    continue
                keep_records.append(record)
            if removed <= 0:
                return 0
            ensure_dir(target.parent)
            with target.open("w", encoding="utf-8", newline="\n") as handle:
                for record in keep_records:
                    handle.write(json.dumps(record, ensure_ascii=True))
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            return removed
