from __future__ import annotations

import hashlib
import json
import logging
import queue
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from backend.session_core_v2.contracts import ALLOWED_TURN_TRANSITIONS, TERMINAL_TURN_STATES
from backend.session_core_v2.errors import SessionCoreError

EventObserver = Callable[[dict[str, Any]], None]

_TIER0_METHODS: frozenset[str] = frozenset(
    {
        "turn/started",
        "item/started",
        "item/agentMessage/delta",
        "item/plan/delta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/textDelta",
        "item/completed",
        "turn/completed",
        "thread/status/changed",
        "thread/started",
        "thread/closed",
        "serverRequest/created",
        "serverRequest/updated",
        "serverRequest/resolved",
    }
)
_TIER1_METHODS: frozenset[str] = frozenset(
    {
        "item/reasoning/summaryPartAdded",
        "item/commandExecution/outputDelta",
        "item/fileChange/outputDelta",
    }
)
_STREAM_TRACE_METHODS: frozenset[str] = frozenset(
    {
        "thread/started",
        "thread/status/changed",
        "thread/closed",
        "turn/started",
        "turn/completed",
        "item/started",
        "item/completed",
        "serverRequest/created",
        "serverRequest/updated",
        "serverRequest/resolved",
        "error",
    }
)
_SERVER_REQUEST_METHODS: frozenset[str] = frozenset(
    {
        "item/tool/requestUserInput",
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
        "mcpServer/elicitation/request",
    }
)
_PENDING_REQUEST_ACTIVE_STATUSES: frozenset[str] = frozenset({"pending", "submitted"})
_SNAPSHOT_TIER0_EVENT_INTERVAL = 200
_SNAPSHOT_TIME_INTERVAL_MS = 10_000
_DAY_MS = 24 * 60 * 60 * 1000

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Subscriber:
    subscriber_id: str
    thread_id: str
    events: queue.Queue[dict[str, Any]]
    lagged: bool = False


class RuntimeStoreV2:
    """Authoritative runtime store for Session Core V2.

    The store is journal-first and uses replay for lossless recovery. It keeps
    an in-memory runtime index and can persist journal/idempotency to sqlite.
    """

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        subscriber_queue_capacity: int = 128,
        retention_max_events: int = 200_000,
        retention_days: int = 7,
    ) -> None:
        self._lock = threading.RLock()
        self._thread_sequences: dict[str, int] = defaultdict(int)
        self._journal: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._snapshot_versions: dict[str, int] = defaultdict(int)
        self._snapshot_last_ms: dict[str, int] = defaultdict(int)
        self._snapshot_payloads: dict[str, dict[str, Any]] = {}
        self._snapshot_last_event_seq: dict[str, int] = defaultdict(int)
        self._tier0_events_since_snapshot: dict[str, int] = defaultdict(int)
        self._subscriber_queue_capacity = max(1, int(subscriber_queue_capacity))
        self._retention_max_events = max(1, int(retention_max_events))
        self._retention_days = max(1, int(retention_days))
        self._retention_window_ms = self._retention_days * _DAY_MS
        self._subscribers: dict[str, _Subscriber] = {}

        self._thread_state: dict[str, dict[str, Any]] = defaultdict(dict)
        self._turns: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._active_turn_by_thread: dict[str, str] = {}
        self._pending_requests: dict[str, dict[str, Any]] = {}
        self._pending_request_by_raw: dict[tuple[str, str], str] = {}
        self._idempotency_mem: dict[tuple[str, str], dict[str, Any]] = {}
        self._legacy_migration_markers: dict[str, dict[str, Any]] = {}
        self._event_observers: list[EventObserver] = []

        self._lagged_reset_count = 0
        self._cursor_expired_count = 0
        self._drop_counts_by_tier: dict[str, int] = defaultdict(int)

        self._db_path = str(Path(db_path).expanduser().resolve()) if db_path else None
        self._db: sqlite3.Connection | None = None
        if self._db_path:
            self._init_db(self._db_path)

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    # ------------------------------------------------------------------
    # Turn runtime state
    # ------------------------------------------------------------------
    def create_turn(self, *, thread_id: str, turn_id: str, status: str = "idle") -> dict[str, Any]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        normalized_turn_id = self._normalize_non_empty(turn_id, "turnId")
        if status not in ALLOWED_TURN_TRANSITIONS:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Unsupported turn status: {status!r}",
                status_code=500,
                details={"status": status},
            )
        with self._lock:
            existing = self._turns[normalized_thread_id].get(normalized_turn_id)
            if existing is not None:
                return self._copy_turn(existing)
            now_ms = self._now_ms()
            turn = {
                "id": normalized_turn_id,
                "threadId": normalized_thread_id,
                "status": status,
                "lastCodexStatus": None,
                "startedAtMs": now_ms,
                "completedAtMs": now_ms if status in TERMINAL_TURN_STATES else None,
                "items": [],
                "error": None,
            }
            self._turns[normalized_thread_id][normalized_turn_id] = turn
            if status not in TERMINAL_TURN_STATES:
                self._active_turn_by_thread[normalized_thread_id] = normalized_turn_id
            self._touch_thread_state_locked(normalized_thread_id, now_ms)
            self._persist_turn(normalized_thread_id, turn)
            return self._copy_turn(turn)

    def transition_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        next_status: str,
        error: dict[str, Any] | None = None,
        last_codex_status: str | None = None,
        allow_same: bool = False,
    ) -> dict[str, Any]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        normalized_turn_id = self._normalize_non_empty(turn_id, "turnId")
        if next_status not in ALLOWED_TURN_TRANSITIONS:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Unsupported turn status: {next_status!r}",
                status_code=500,
                details={"status": next_status},
            )
        with self._lock:
            turn = self._turns[normalized_thread_id].get(normalized_turn_id)
            if turn is None:
                turn = self.create_turn(
                    thread_id=normalized_thread_id,
                    turn_id=normalized_turn_id,
                    status="idle",
                )
                self._turns[normalized_thread_id][normalized_turn_id] = turn
            current_status = str(turn.get("status") or "idle")
            if current_status == next_status and allow_same:
                if last_codex_status is not None:
                    turn["lastCodexStatus"] = str(last_codex_status)
                if error is not None:
                    turn["error"] = error
                self._persist_turn(normalized_thread_id, turn)
                return self._copy_turn(turn)

            if current_status in TERMINAL_TURN_STATES:
                raise SessionCoreError(
                    code="ERR_TURN_TERMINAL",
                    message=f"Turn {normalized_turn_id} is terminal.",
                    status_code=409,
                    details={"threadId": normalized_thread_id, "turnId": normalized_turn_id, "status": current_status},
                )

            allowed = ALLOWED_TURN_TRANSITIONS.get(current_status, frozenset())
            if next_status not in allowed:
                raise SessionCoreError(
                    code="ERR_TURN_NOT_STEERABLE",
                    message=f"Illegal turn transition: {current_status} -> {next_status}.",
                    status_code=409,
                    details={
                        "threadId": normalized_thread_id,
                        "turnId": normalized_turn_id,
                        "from": current_status,
                        "to": next_status,
                    },
                )

            now_ms = self._now_ms()
            turn["status"] = next_status
            if last_codex_status is not None:
                turn["lastCodexStatus"] = str(last_codex_status)
            if error is not None:
                turn["error"] = error
            if next_status in TERMINAL_TURN_STATES:
                turn["completedAtMs"] = now_ms
                if self._active_turn_by_thread.get(normalized_thread_id) == normalized_turn_id:
                    self._active_turn_by_thread.pop(normalized_thread_id, None)
            else:
                self._active_turn_by_thread[normalized_thread_id] = normalized_turn_id
            self._touch_thread_state_locked(normalized_thread_id, now_ms)
            self._persist_turn(normalized_thread_id, turn)
            return self._copy_turn(turn)

    def get_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any] | None:
        normalized_thread_id = str(thread_id or "").strip()
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_thread_id or not normalized_turn_id:
            return None
        with self._lock:
            turn = self._turns.get(normalized_thread_id, {}).get(normalized_turn_id)
            if turn is None:
                return None
            return self._copy_turn(turn)

    def get_active_turn(self, *, thread_id: str) -> dict[str, Any] | None:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return None
        with self._lock:
            active_turn_id = self._active_turn_by_thread.get(normalized_thread_id)
            if not active_turn_id:
                return None
            turn = self._turns.get(normalized_thread_id, {}).get(active_turn_id)
            if turn is None:
                return None
            return self._copy_turn(turn)

    def list_turns(self, *, thread_id: str) -> list[dict[str, Any]]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return []
        with self._lock:
            turns = [
                self._copy_turn(turn)
                for turn in self._turns.get(normalized_thread_id, {}).values()
                if isinstance(turn, dict)
            ]
        return sorted(
            turns,
            key=lambda turn: (
                int(turn.get("startedAtMs") or 0),
                str(turn.get("id") or ""),
            ),
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------
    def resolve_idempotent_result(self, *, action_type: str, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        normalized_action = self._normalize_non_empty(action_type, "actionType")
        normalized_key = self._normalize_non_empty(key, "idempotencyKey")
        payload_hash = self._payload_hash(payload)
        with self._lock:
            record = self._idempotency_mem.get((normalized_action, normalized_key))
            if record is None:
                record = self._load_idempotency_from_db(normalized_action, normalized_key)
                if record is not None:
                    self._idempotency_mem[(normalized_action, normalized_key)] = record
            if record is None:
                return None
            if record["payload_hash"] != payload_hash:
                raise SessionCoreError(
                    code="ERR_IDEMPOTENCY_PAYLOAD_MISMATCH",
                    message="Idempotency key already used with a different payload.",
                    status_code=409,
                    details={"actionType": normalized_action, "key": normalized_key},
                )
            return json.loads(record["response_json"])

    def record_idempotent_result(
        self,
        *,
        action_type: str,
        key: str,
        payload: dict[str, Any],
        response: dict[str, Any],
        thread_id: str | None = None,
        turn_id: str | None = None,
        request_id: str | None = None,
        journal_event_seq: int | None = None,
    ) -> None:
        normalized_action = self._normalize_non_empty(action_type, "actionType")
        normalized_key = self._normalize_non_empty(key, "idempotencyKey")
        payload_hash = self._payload_hash(payload)
        response_json = json.dumps(response, ensure_ascii=True, sort_keys=True)
        response_hash = hashlib.sha256(response_json.encode("utf-8")).hexdigest()
        accepted_at_ms = self._now_ms()
        record = {
            "payload_hash": payload_hash,
            "response_json": response_json,
            "response_hash": response_hash,
            "thread_id": thread_id or "",
            "turn_id": turn_id or "",
            "request_id": request_id or "",
            "accepted_at_ms": accepted_at_ms,
            "journal_event_seq": int(journal_event_seq) if journal_event_seq is not None else None,
        }
        with self._lock:
            self._idempotency_mem[(normalized_action, normalized_key)] = record
            self._persist_idempotency_record(normalized_action, normalized_key, record)

    # ------------------------------------------------------------------
    # Legacy migration markers
    # ------------------------------------------------------------------
    def has_legacy_migration_marker(self, *, thread_id: str) -> bool:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return False
        with self._lock:
            if normalized_thread_id in self._legacy_migration_markers:
                return True
            record = self._load_legacy_migration_marker_from_db(normalized_thread_id)
            if record is not None:
                self._legacy_migration_markers[normalized_thread_id] = record
                return True
            return False

    def read_legacy_migration_marker(self, *, thread_id: str) -> dict[str, Any] | None:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return None
        with self._lock:
            record = self._legacy_migration_markers.get(normalized_thread_id)
            if record is not None:
                return dict(record)
            loaded = self._load_legacy_migration_marker_from_db(normalized_thread_id)
            if loaded is None:
                return None
            self._legacy_migration_markers[normalized_thread_id] = loaded
            return dict(loaded)

    def mark_legacy_thread_migrated(
        self,
        *,
        thread_id: str,
        source_project_id: str | None = None,
        source_node_id: str | None = None,
        source_role: str | None = None,
        source_snapshot_version: int | None = None,
        source_item_count: int | None = None,
        source_pending_request_count: int | None = None,
        source_hash: str | None = None,
    ) -> dict[str, Any]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        record = {
            "threadId": normalized_thread_id,
            "migratedAtMs": self._now_ms(),
            "sourceProjectId": str(source_project_id or "").strip() or None,
            "sourceNodeId": str(source_node_id or "").strip() or None,
            "sourceRole": str(source_role or "").strip() or None,
            "sourceSnapshotVersion": int(source_snapshot_version) if source_snapshot_version is not None else None,
            "sourceItemCount": int(source_item_count) if source_item_count is not None else None,
            "sourcePendingRequestCount": (
                int(source_pending_request_count)
                if source_pending_request_count is not None
                else None
            ),
            "sourceHash": str(source_hash or "").strip() or None,
        }
        with self._lock:
            existing = self._legacy_migration_markers.get(normalized_thread_id)
            if existing is not None:
                return dict(existing)
            from_db = self._load_legacy_migration_marker_from_db(normalized_thread_id)
            if from_db is not None:
                self._legacy_migration_markers[normalized_thread_id] = from_db
                return dict(from_db)
            self._legacy_migration_markers[normalized_thread_id] = record
            self._persist_legacy_migration_marker(record)
            return dict(record)

    # ------------------------------------------------------------------
    # Pending server requests
    # ------------------------------------------------------------------
    def register_pending_server_request(
        self,
        *,
        raw_request_id: Any,
        method: str,
        thread_id: str,
        turn_id: str | None,
        item_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_method = self._normalize_non_empty(method, "method")
        if normalized_method not in _SERVER_REQUEST_METHODS:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Unsupported server request method: {normalized_method!r}",
                status_code=400,
                details={"method": normalized_method},
            )
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        normalized_turn_id = self._optional_non_empty(turn_id)
        normalized_item_id = str(item_id or "").strip() or None
        raw_request_json = self._serialize_raw_request_id(raw_request_id)
        now_ms = self._now_ms()
        with self._lock:
            existing_id = self._pending_request_by_raw.get((normalized_thread_id, raw_request_json))
            if existing_id:
                existing = self._pending_requests.get(existing_id)
                if existing is not None:
                    existing_status = str(existing.get("status") or "")
                    if existing_status in _PENDING_REQUEST_ACTIVE_STATUSES:
                        return self._pending_request_public(existing)
                self._pending_request_by_raw.pop((normalized_thread_id, raw_request_json), None)

            request_id = str(uuid.uuid4())
            record = {
                "requestId": request_id,
                "rawRequestIdJson": raw_request_json,
                "method": normalized_method,
                "threadId": normalized_thread_id,
                "turnId": normalized_turn_id,
                "itemId": normalized_item_id,
                "status": "pending",
                "submissionKind": None,
                "createdAtMs": now_ms,
                "submittedAtMs": None,
                "resolvedAtMs": None,
                "payload": dict(payload),
            }
            self._pending_requests[request_id] = record
            self._pending_request_by_raw[(normalized_thread_id, raw_request_json)] = request_id
            self._persist_pending_request(record)

            turn = self._turns.get(normalized_thread_id, {}).get(normalized_turn_id or "")
            if normalized_turn_id and isinstance(turn, dict):
                turn_status = str(turn.get("status") or "")
                if turn_status == "inProgress":
                    try:
                        self.transition_turn(
                            thread_id=normalized_thread_id,
                            turn_id=normalized_turn_id,
                            next_status="waitingUserInput",
                            allow_same=True,
                        )
                    except SessionCoreError:
                        logger.debug(
                            "session_core_v2 failed to move turn to waitingUserInput on pending request",
                            exc_info=True,
                        )

            self._append_pending_request_event_locked(method="serverRequest/created", record=record)
            return self._pending_request_public(record)

    def list_pending_server_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            records = [
                self._pending_request_public(record)
                for record in self._pending_requests.values()
                if str(record.get("status") or "") in _PENDING_REQUEST_ACTIVE_STATUSES
            ]
        records.sort(key=lambda entry: (int(entry.get("createdAtMs") or 0), str(entry.get("requestId") or "")))
        return records

    def get_pending_server_request(self, *, request_id: str) -> dict[str, Any] | None:
        normalized_request_id = str(request_id or "").strip()
        if not normalized_request_id:
            return None
        with self._lock:
            record = self._pending_requests.get(normalized_request_id)
            if record is None:
                return None
            return dict(record)

    def pending_server_request_raw_id(self, *, request_id: str) -> Any:
        record = self.get_pending_server_request(request_id=request_id)
        if record is None:
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {request_id} is not pending.",
                status_code=409,
                details={"requestId": str(request_id or "")},
            )
        raw_request_json = str(record.get("rawRequestIdJson") or "").strip()
        if not raw_request_json:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="Pending request is missing raw request id.",
                status_code=500,
                details={"requestId": str(request_id or "")},
            )
        return self._deserialize_raw_request_id(raw_request_json)

    def mark_pending_server_request_submitted(self, *, request_id: str, submission_kind: str) -> dict[str, Any]:
        normalized_request_id = self._normalize_non_empty(request_id, "requestId")
        normalized_kind = self._normalize_non_empty(submission_kind, "submissionKind")
        if normalized_kind not in {"resolve", "reject"}:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Unsupported submission kind: {normalized_kind!r}",
                status_code=500,
                details={"submissionKind": normalized_kind},
            )
        with self._lock:
            record = self._pending_requests.get(normalized_request_id)
            if record is None:
                raise SessionCoreError(
                    code="ERR_REQUEST_STALE",
                    message=f"Request {normalized_request_id} is not pending.",
                    status_code=409,
                    details={"requestId": normalized_request_id},
                )
            current_status = str(record.get("status") or "")
            if current_status not in _PENDING_REQUEST_ACTIVE_STATUSES:
                raise SessionCoreError(
                    code="ERR_REQUEST_STALE",
                    message=f"Request {normalized_request_id} is no longer active.",
                    status_code=409,
                    details={"requestId": normalized_request_id, "status": current_status},
                )
            now_ms = self._now_ms()
            record["status"] = "submitted"
            record["submissionKind"] = normalized_kind
            record["submittedAtMs"] = now_ms
            self._persist_pending_request(record)
            self._append_pending_request_event_locked(method="serverRequest/updated", record=record)
            return self._pending_request_public(record)

    def expire_pending_server_requests_for_new_session(self) -> int:
        with self._lock:
            pending_ids = [
                request_id
                for request_id, record in self._pending_requests.items()
                if str(record.get("status") or "") in _PENDING_REQUEST_ACTIVE_STATUSES
            ]
            if not pending_ids:
                return 0
            now_ms = self._now_ms()
            touched_turns: set[tuple[str, str]] = set()
            for request_id in pending_ids:
                record = self._pending_requests[request_id]
                record["status"] = "expired"
                record["resolvedAtMs"] = now_ms
                self._persist_pending_request(record)
                raw_request_json = str(record.get("rawRequestIdJson") or "").strip()
                thread_id = str(record.get("threadId") or "").strip()
                if thread_id and raw_request_json:
                    self._pending_request_by_raw.pop((thread_id, raw_request_json), None)
                self._append_pending_request_event_locked(method="serverRequest/updated", record=record)
                turn_id = str(record.get("turnId") or "").strip()
                if thread_id and turn_id:
                    touched_turns.add((thread_id, turn_id))
            for thread_id, turn_id in touched_turns:
                self._resume_turn_if_no_unresolved_requests(thread_id=thread_id, turn_id=turn_id)
            return len(pending_ids)

    def resolve_pending_server_request_from_notification(
        self,
        *,
        thread_id: str,
        raw_request_id: Any,
    ) -> dict[str, Any] | None:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        raw_request_json = self._serialize_raw_request_id(raw_request_id)
        with self._lock:
            request_id = self._pending_request_by_raw.get((normalized_thread_id, raw_request_json))
            if not request_id:
                return None
            record = self._pending_requests.get(request_id)
            if record is None:
                return None
            current_status = str(record.get("status") or "")
            if current_status in {"resolved", "rejected", "expired"}:
                return self._pending_request_public(record)
            now_ms = self._now_ms()
            if current_status == "submitted":
                submission_kind = str(record.get("submissionKind") or "")
                record["status"] = "resolved" if submission_kind == "resolve" else "rejected"
            else:
                record["status"] = "expired"
            record["resolvedAtMs"] = now_ms
            self._persist_pending_request(record)
            self._pending_request_by_raw.pop((normalized_thread_id, raw_request_json), None)
            turn_id = str(record.get("turnId") or "").strip()
            if turn_id:
                self._resume_turn_if_no_unresolved_requests(thread_id=normalized_thread_id, turn_id=turn_id)
            return self._pending_request_public(record)

    # ------------------------------------------------------------------
    # Event ingest + journal + replay
    # ------------------------------------------------------------------
    def append_thread_event(self, *, thread_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.append_notification(method=method, params=params, thread_id_override=thread_id)

    def append_notification(
        self,
        *,
        method: str,
        params: dict[str, Any],
        thread_id_override: str | None = None,
    ) -> dict[str, Any]:
        normalized_method = str(method or "").strip()
        if not normalized_method:
            return {}
        normalized_thread_id = (
            str(thread_id_override or "").strip()
            or self._extract_thread_id(params)
        )
        if not normalized_thread_id:
            return {}
        turn_id = self._extract_turn_id(params)
        normalized_params = dict(params)
        if normalized_method == "serverRequest/resolved":
            raw_request_id = normalized_params.get("requestId")
            if raw_request_id is not None:
                request_record = self.resolve_pending_server_request_from_notification(
                    thread_id=normalized_thread_id,
                    raw_request_id=raw_request_id,
                )
                if request_record is not None:
                    normalized_params["request"] = request_record
                    if not turn_id:
                        turn_id = self._optional_non_empty(request_record.get("turnId"))
        self._record_thread_state_from_notification(
            thread_id=normalized_thread_id,
            method=normalized_method,
            params=normalized_params,
        )
        self._apply_notification_to_runtime_state(
            thread_id=normalized_thread_id,
            turn_id=turn_id,
            method=normalized_method,
            params=normalized_params,
        )
        if normalized_method == "turn/started":
            resolved_turn_id = (
                turn_id
                or self._extract_turn_id(normalized_params)
                or ""
            )
            if resolved_turn_id:
                turn_payload = normalized_params.get("turn")
                return self.append_turn_started_if_absent(
                    thread_id=normalized_thread_id,
                    turn_id=resolved_turn_id,
                    turn=turn_payload if isinstance(turn_payload, dict) else None,
                    params=normalized_params,
                )
        return self.append_event(
            thread_id=normalized_thread_id,
            method=normalized_method,
            params=normalized_params,
            turn_id=turn_id,
            source="journal",
            replayable=True,
        )

    def append_turn_started_if_absent(
        self,
        *,
        thread_id: str,
        turn_id: str,
        turn: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        normalized_turn_id = self._normalize_non_empty(turn_id, "turnId")
        payload_params = dict(params or {})
        payload_turn: dict[str, Any]
        if isinstance(payload_params.get("turn"), dict):
            payload_turn = dict(payload_params["turn"])
        elif isinstance(turn, dict):
            payload_turn = dict(turn)
        else:
            payload_turn = {"id": normalized_turn_id}
        if not str(payload_turn.get("id") or "").strip():
            payload_turn["id"] = normalized_turn_id
        payload_params["turn"] = payload_turn

        with self._lock:
            existing = self._find_event_by_method_and_turn_locked(
                thread_id=normalized_thread_id,
                method="turn/started",
                turn_id=normalized_turn_id,
            )
            if existing is not None:
                return dict(existing)
        return self.append_event(
            thread_id=normalized_thread_id,
            method="turn/started",
            params=payload_params,
            turn_id=normalized_turn_id,
            source="journal",
            replayable=True,
            tier="tier0",
        )

    def append_event(
        self,
        *,
        thread_id: str,
        method: str,
        params: dict[str, Any],
        turn_id: str | None,
        source: str,
        replayable: bool,
        tier: str | None = None,
    ) -> dict[str, Any]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        normalized_method = self._normalize_non_empty(method, "method")
        normalized_turn_id = str(turn_id or "").strip() or None
        normalized_source = "replay" if source == "replay" else "journal"
        normalized_tier = tier or self._resolve_event_tier(normalized_method)
        occurred_at_ms = self._now_ms()

        with self._lock:
            next_seq = self._thread_sequences[normalized_thread_id] + 1
            self._thread_sequences[normalized_thread_id] = next_seq
            snapshot_version = self._maybe_update_snapshot(
                thread_id=normalized_thread_id,
                event_seq=next_seq,
                now_ms=occurred_at_ms,
                tier=normalized_tier,
            )
            event = {
                "schemaVersion": 1,
                "eventId": f"{normalized_thread_id}:{next_seq}",
                "eventSeq": next_seq,
                "tier": normalized_tier,
                "method": normalized_method,
                "threadId": normalized_thread_id,
                "turnId": normalized_turn_id,
                "occurredAtMs": occurred_at_ms,
                "replayable": bool(replayable),
                "snapshotVersion": snapshot_version,
                "source": normalized_source,
                "params": dict(params),
            }
            if self._db is None:
                self._journal[normalized_thread_id].append(event)
                self._trim_memory_journal(normalized_thread_id, now_ms=occurred_at_ms)
            self._persist_event(event)
            self._fanout_event(event)
            thread_subscriber_count = self._subscriber_count_for_thread_locked(normalized_thread_id)
            event_copy = dict(event)
        if normalized_method in _STREAM_TRACE_METHODS:
            logger.info(
                "session_core_v2 journal append",
                extra={
                    "threadId": normalized_thread_id,
                    "turnId": normalized_turn_id,
                    "eventSeq": next_seq,
                    "method": normalized_method,
                    "tier": normalized_tier,
                    "replayable": bool(replayable),
                    "threadSubscriberCount": thread_subscriber_count,
                },
            )
        self._notify_event_observers(event_copy)
        return event_copy

    def add_event_observer(self, observer: EventObserver) -> None:
        if observer is None:
            return
        with self._lock:
            self._event_observers.append(observer)

    def _notify_event_observers(self, event: dict[str, Any]) -> None:
        with self._lock:
            observers = list(self._event_observers)
        for observer in observers:
            try:
                observer(dict(event))
            except Exception:
                logger.exception("session_core_v2 event observer failed")

    def parse_cursor(self, *, thread_id: str, cursor: str | None) -> int:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        if cursor is None or str(cursor).strip() == "":
            return 0
        raw_cursor = str(cursor).strip()
        candidate = raw_cursor
        if ":" in candidate:
            candidate = candidate.rsplit(":", 1)[1]
        try:
            cursor_value = int(candidate)
        except ValueError as exc:
            raise SessionCoreError(
                code="ERR_CURSOR_INVALID",
                message="Cursor must be an integer event sequence.",
                status_code=409,
                details={"threadId": normalized_thread_id, "cursor": raw_cursor},
            ) from exc
        if cursor_value < 0:
            raise SessionCoreError(
                code="ERR_CURSOR_INVALID",
                message="Cursor cannot be negative.",
                status_code=409,
                details={"threadId": normalized_thread_id, "cursor": raw_cursor},
            )
        self._assert_cursor_available(thread_id=normalized_thread_id, cursor_value=cursor_value)
        return cursor_value

    def replay_events(self, *, thread_id: str, cursor_value: int) -> list[dict[str, Any]]:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        with self._lock:
            events = self._read_journal_events_locked(normalized_thread_id, after_event_seq=cursor_value)
        replayed: list[dict[str, Any]] = []
        for event in events:
            copied = dict(event)
            copied["source"] = "replay"
            replayed.append(copied)
        return replayed

    def read_thread_journal(self, thread_id: str) -> list[dict[str, Any]]:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return []
        with self._lock:
            return self._read_journal_events_locked(normalized_thread_id, after_event_seq=0)

    def list_thread_ids_with_history(self) -> list[str]:
        with self._lock:
            thread_ids: set[str] = set()
            thread_ids.update(thread_id for thread_id in self._journal if str(thread_id or "").strip())
            thread_ids.update(thread_id for thread_id in self._turns if str(thread_id or "").strip())
            thread_ids.update(thread_id for thread_id in self._snapshot_payloads if str(thread_id or "").strip())
            if self._db is not None:
                rows = self._db.execute(
                    """
                    SELECT thread_id, MAX(last_seen_ms) AS last_seen_ms
                    FROM (
                        SELECT thread_id, MAX(occurred_at_ms) AS last_seen_ms FROM session_v2_journal GROUP BY thread_id
                        UNION ALL
                        SELECT thread_id, MAX(last_updated_ms) AS last_seen_ms FROM session_v2_turns GROUP BY thread_id
                        UNION ALL
                        SELECT thread_id, MAX(updated_at_ms) AS last_seen_ms FROM session_v2_snapshots GROUP BY thread_id
                    )
                    WHERE thread_id IS NOT NULL AND thread_id != ''
                    GROUP BY thread_id
                    ORDER BY last_seen_ms DESC
                    """
                ).fetchall()
                ordered: list[str] = []
                for row in rows:
                    thread_id = str(row["thread_id"] or "").strip()
                    if thread_id:
                        ordered.append(thread_id)
                        thread_ids.discard(thread_id)
                ordered.extend(sorted(thread_ids))
                return ordered
        return []

    # ------------------------------------------------------------------
    # Event streaming subscribers
    # ------------------------------------------------------------------
    def subscribe_thread_events(self, *, thread_id: str) -> str:
        normalized_thread_id = self._normalize_non_empty(thread_id, "threadId")
        subscriber_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[subscriber_id] = _Subscriber(
                subscriber_id=subscriber_id,
                thread_id=normalized_thread_id,
                events=queue.Queue(maxsize=self._subscriber_queue_capacity),
            )
            thread_subscriber_count = self._subscriber_count_for_thread_locked(normalized_thread_id)
            total_subscriber_count = len(self._subscribers)
        logger.info(
            "session_core_v2 stream subscriber opened",
            extra={
                "threadId": normalized_thread_id,
                "subscriberId": subscriber_id,
                "threadSubscriberCount": thread_subscriber_count,
                "totalSubscriberCount": total_subscriber_count,
            },
        )
        return subscriber_id

    def read_subscriber_event(self, *, subscriber_id: str, timeout_sec: float) -> dict[str, Any] | None:
        with self._lock:
            subscriber = self._subscribers.get(subscriber_id)
        if subscriber is None:
            logger.info(
                "session_core_v2 stream subscriber missing",
                extra={"subscriberId": subscriber_id},
            )
            return None
        try:
            event = subscriber.events.get(timeout=max(0.1, float(timeout_sec)))
        except queue.Empty:
            return {}
        if isinstance(event, dict) and event.get("__control") == "lagged":
            logger.warning(
                "session_core_v2 stream lagged control dequeued",
                extra={
                    "threadId": subscriber.thread_id,
                    "subscriberId": subscriber_id,
                    "skipped": event.get("skipped"),
                },
            )
            return event
        method = str(event.get("method") or "") if isinstance(event, dict) else ""
        if method in _STREAM_TRACE_METHODS:
            logger.info(
                "session_core_v2 stream dequeue",
                extra={
                    "threadId": subscriber.thread_id,
                    "subscriberId": subscriber_id,
                    "eventSeq": event.get("eventSeq") if isinstance(event, dict) else None,
                    "method": method,
                },
            )
        return event

    def unsubscribe(self, *, subscriber_id: str) -> None:
        with self._lock:
            subscriber = self._subscribers.pop(subscriber_id, None)
            total_subscriber_count = len(self._subscribers)
            thread_subscriber_count = (
                self._subscriber_count_for_thread_locked(subscriber.thread_id)
                if subscriber is not None
                else 0
            )
        if subscriber is not None:
            logger.info(
                "session_core_v2 stream subscriber closed",
                extra={
                    "threadId": subscriber.thread_id,
                    "subscriberId": subscriber_id,
                    "threadSubscriberCount": thread_subscriber_count,
                    "totalSubscriberCount": total_subscriber_count,
                },
            )

    def metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            queue_depth = 0
            for subscriber in self._subscribers.values():
                queue_depth = max(queue_depth, subscriber.events.qsize())
            return {
                "queueDepth": queue_depth,
                "subscriberCount": len(self._subscribers),
                "laggedResetCount": self._lagged_reset_count,
                "cursorExpiredCount": self._cursor_expired_count,
                "dropCountsByTier": dict(self._drop_counts_by_tier),
            }

    # ------------------------------------------------------------------
    # Internal: runtime state updates from notifications
    # ------------------------------------------------------------------
    def _apply_notification_to_runtime_state(
        self,
        *,
        thread_id: str,
        turn_id: str | None,
        method: str,
        params: dict[str, Any],
    ) -> None:
        if method == "turn/started":
            started_turn = self._extract_turn_id(params)
            if started_turn:
                self.create_turn(thread_id=thread_id, turn_id=started_turn, status="inProgress")
            return

        if method == "item/started":
            if turn_id:
                if self.get_turn(thread_id=thread_id, turn_id=turn_id) is None:
                    self.create_turn(thread_id=thread_id, turn_id=turn_id, status="idle")
                self.transition_turn(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    next_status="inProgress",
                    allow_same=True,
                )
                self._upsert_item(thread_id=thread_id, turn_id=turn_id, params=params, completed=False)
            return

        if method == "item/completed":
            if turn_id:
                self._upsert_item(thread_id=thread_id, turn_id=turn_id, params=params, completed=True)
            return

        if method == "turn/completed":
            payload_turn = params.get("turn")
            if not isinstance(payload_turn, dict):
                return
            completed_turn_id = str(payload_turn.get("id") or turn_id or "").strip()
            if not completed_turn_id:
                return
            completed_status = str(payload_turn.get("status") or "completed")
            if completed_status not in {"inProgress", "completed", "failed", "interrupted"}:
                completed_status = "failed"
            if self.get_turn(thread_id=thread_id, turn_id=completed_turn_id) is None:
                initial_status = "inProgress" if completed_status == "inProgress" else completed_status
                self.create_turn(thread_id=thread_id, turn_id=completed_turn_id, status=initial_status)
            terminal_error = payload_turn.get("error")
            if completed_status == "inProgress":
                self.transition_turn(
                    thread_id=thread_id,
                    turn_id=completed_turn_id,
                    next_status="inProgress",
                    allow_same=True,
                    last_codex_status=completed_status,
                )
            else:
                self.transition_turn(
                    thread_id=thread_id,
                    turn_id=completed_turn_id,
                    next_status=completed_status,
                    allow_same=True,
                    last_codex_status=completed_status,
                    error=terminal_error if isinstance(terminal_error, dict) else None,
                )
            return

        if method == "serverRequest/resolved":
            raw_request_id = params.get("requestId")
            if raw_request_id is None:
                return
            self.resolve_pending_server_request_from_notification(
                thread_id=thread_id,
                raw_request_id=raw_request_id,
            )
            return

        if method == "error" and turn_id:
            turn = self.get_turn(thread_id=thread_id, turn_id=turn_id)
            if turn and str(turn.get("status")) not in TERMINAL_TURN_STATES:
                self.transition_turn(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    next_status="failed",
                    allow_same=True,
                    error={"code": "ERR_INTERNAL", "message": "Runtime error notification.", "details": params},
                )

    def _upsert_item(self, *, thread_id: str, turn_id: str, params: dict[str, Any], completed: bool) -> None:
        item = params.get("item")
        if not isinstance(item, dict):
            return
        turn = self._turns.get(thread_id, {}).get(turn_id)
        if turn is None:
            return
        items = turn.get("items")
        if not isinstance(items, list):
            items = []
            turn["items"] = items
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            return
        existing_index: int | None = None
        for idx, existing in enumerate(items):
            if isinstance(existing, dict) and str(existing.get("id") or "").strip() == item_id:
                existing_index = idx
                break
        payload_item = dict(item)
        payload_status = payload_item.get("status")
        if not isinstance(payload_status, str):
            payload_status = "completed" if completed else "inProgress"
        payload_item["status"] = payload_status
        if existing_index is None:
            items.append(payload_item)
        else:
            items[existing_index] = payload_item
        self._persist_turn(thread_id, turn)

    # ------------------------------------------------------------------
    # Internal: DB + journal helpers
    # ------------------------------------------------------------------
    def _init_db(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_v2_journal (
                thread_id TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                occurred_at_ms INTEGER NOT NULL DEFAULT 0,
                event_json TEXT NOT NULL,
                PRIMARY KEY(thread_id, event_seq)
            );

            CREATE TABLE IF NOT EXISTS session_v2_idempotency (
                action_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                response_hash TEXT NOT NULL,
                thread_id TEXT,
                turn_id TEXT,
                request_id TEXT,
                accepted_at_ms INTEGER NOT NULL,
                journal_event_seq INTEGER,
                PRIMARY KEY(action_type, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS session_v2_turns (
                thread_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                status TEXT NOT NULL,
                turn_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                last_updated_ms INTEGER NOT NULL,
                PRIMARY KEY(thread_id, turn_id)
            );

            CREATE TABLE IF NOT EXISTS session_v2_pending_requests (
                request_id TEXT PRIMARY KEY,
                raw_request_id_json TEXT NOT NULL,
                method TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                turn_id TEXT,
                item_id TEXT,
                status TEXT NOT NULL,
                submission_kind TEXT,
                created_at_ms INTEGER NOT NULL,
                submitted_at_ms INTEGER,
                resolved_at_ms INTEGER,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_v2_snapshots (
                thread_id TEXT PRIMARY KEY,
                snapshot_version INTEGER NOT NULL,
                last_event_seq INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS session_v2_legacy_migrations (
                thread_id TEXT PRIMARY KEY,
                migrated_at_ms INTEGER NOT NULL,
                source_project_id TEXT,
                source_node_id TEXT,
                source_role TEXT,
                source_snapshot_version INTEGER,
                source_item_count INTEGER,
                source_pending_request_count INTEGER,
                source_hash TEXT
            );
            """
        )
        self._ensure_pending_requests_turn_id_nullable(connection)
        self._ensure_column(connection, "session_v2_journal", "occurred_at_ms", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(connection, "session_v2_snapshots", "snapshot_json", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column(connection, "session_v2_pending_requests", "submission_kind", "TEXT")
        self._ensure_column(connection, "session_v2_pending_requests", "submitted_at_ms", "INTEGER")
        self._ensure_column(connection, "session_v2_pending_requests", "resolved_at_ms", "INTEGER")
        connection.commit()
        self._db = connection
        self._backfill_journal_occurred_at_ms()
        self._bootstrap_from_db()

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(str(row["name"]) == column for row in rows):
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    @staticmethod
    def _ensure_pending_requests_turn_id_nullable(connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(session_v2_pending_requests)").fetchall()
        existing_columns = {str(row["name"]) for row in rows}
        turn_id_row = None
        for row in rows:
            if str(row["name"]) == "turn_id":
                turn_id_row = row
                break
        if turn_id_row is None:
            return
        if int(turn_id_row["notnull"] or 0) == 0:
            return

        submission_kind_expr = "submission_kind" if "submission_kind" in existing_columns else "NULL"
        created_at_expr = "created_at_ms" if "created_at_ms" in existing_columns else "0"
        submitted_at_expr = "submitted_at_ms" if "submitted_at_ms" in existing_columns else "NULL"
        resolved_at_expr = "resolved_at_ms" if "resolved_at_ms" in existing_columns else "NULL"

        connection.execute("BEGIN")
        try:
            connection.execute(
                """
                CREATE TABLE session_v2_pending_requests_new (
                    request_id TEXT PRIMARY KEY,
                    raw_request_id_json TEXT NOT NULL,
                    method TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    turn_id TEXT,
                    item_id TEXT,
                    status TEXT NOT NULL,
                    submission_kind TEXT,
                    created_at_ms INTEGER NOT NULL,
                    submitted_at_ms INTEGER,
                    resolved_at_ms INTEGER,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO session_v2_pending_requests_new(
                    request_id,
                    raw_request_id_json,
                    method,
                    thread_id,
                    turn_id,
                    item_id,
                    status,
                    submission_kind,
                    created_at_ms,
                    submitted_at_ms,
                    resolved_at_ms,
                    payload_json
                )
                SELECT
                    request_id,
                    raw_request_id_json,
                    method,
                    thread_id,
                    CASE
                        WHEN turn_id IS NULL OR TRIM(turn_id) = '' THEN NULL
                        ELSE turn_id
                    END AS turn_id,
                    item_id,
                    status,
                    {submission_kind_expr},
                    {created_at_expr},
                    {submitted_at_expr},
                    {resolved_at_expr},
                    payload_json
                FROM session_v2_pending_requests
                """.format(
                    submission_kind_expr=submission_kind_expr,
                    created_at_expr=created_at_expr,
                    submitted_at_expr=submitted_at_expr,
                    resolved_at_expr=resolved_at_expr,
                )
            )
            connection.execute("DROP TABLE session_v2_pending_requests")
            connection.execute("ALTER TABLE session_v2_pending_requests_new RENAME TO session_v2_pending_requests")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    def _backfill_journal_occurred_at_ms(self) -> None:
        if self._db is None:
            return
        rows = self._db.execute(
            """
            SELECT thread_id, event_seq, event_json
            FROM session_v2_journal
            WHERE occurred_at_ms <= 0
            """
        ).fetchall()
        if not rows:
            return
        updates: list[tuple[int, str, int]] = []
        for row in rows:
            thread_id = str(row["thread_id"] or "")
            event_seq = int(row["event_seq"] or 0)
            if not thread_id or event_seq <= 0:
                continue
            occurred_at_ms = 0
            try:
                payload = json.loads(str(row["event_json"] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                occurred_at_ms = int(payload.get("occurredAtMs") or 0)
            if occurred_at_ms <= 0:
                occurred_at_ms = self._now_ms()
            updates.append((occurred_at_ms, thread_id, event_seq))
        if not updates:
            return
        self._db.executemany(
            """
            UPDATE session_v2_journal
            SET occurred_at_ms = ?
            WHERE thread_id = ? AND event_seq = ?
            """,
            updates,
        )
        self._db.commit()

    def _bootstrap_from_db(self) -> None:
        if self._db is None:
            return
        rows = self._db.execute(
            "SELECT thread_id, MAX(event_seq) AS max_seq FROM session_v2_journal GROUP BY thread_id"
        ).fetchall()
        for row in rows:
            thread_id = str(row["thread_id"] or "").strip()
            if not thread_id:
                continue
            self._thread_sequences[thread_id] = int(row["max_seq"] or 0)

        snapshot_rows = self._db.execute(
            "SELECT thread_id, snapshot_version, last_event_seq, updated_at_ms, snapshot_json FROM session_v2_snapshots"
        ).fetchall()
        for row in snapshot_rows:
            thread_id = str(row["thread_id"] or "").strip()
            if not thread_id:
                continue
            self._snapshot_versions[thread_id] = int(row["snapshot_version"] or 0)
            self._snapshot_last_event_seq[thread_id] = int(row["last_event_seq"] or 0)
            self._snapshot_last_ms[thread_id] = int(row["updated_at_ms"] or 0)
            try:
                payload = json.loads(str(row["snapshot_json"] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                self._snapshot_payloads[thread_id] = payload
                thread_payload = payload.get("thread")
                if isinstance(thread_payload, dict):
                    self._thread_state[thread_id] = dict(thread_payload)

        legacy_migration_rows = self._db.execute(
            """
            SELECT
                thread_id,
                migrated_at_ms,
                source_project_id,
                source_node_id,
                source_role,
                source_snapshot_version,
                source_item_count,
                source_pending_request_count,
                source_hash
            FROM session_v2_legacy_migrations
            """
        ).fetchall()
        for row in legacy_migration_rows:
            thread_id = str(row["thread_id"] or "").strip()
            if not thread_id:
                continue
            self._legacy_migration_markers[thread_id] = {
                "threadId": thread_id,
                "migratedAtMs": int(row["migrated_at_ms"] or 0),
                "sourceProjectId": str(row["source_project_id"] or "").strip() or None,
                "sourceNodeId": str(row["source_node_id"] or "").strip() or None,
                "sourceRole": str(row["source_role"] or "").strip() or None,
                "sourceSnapshotVersion": (
                    int(row["source_snapshot_version"])
                    if row["source_snapshot_version"] is not None
                    else None
                ),
                "sourceItemCount": (
                    int(row["source_item_count"])
                    if row["source_item_count"] is not None
                    else None
                ),
                "sourcePendingRequestCount": (
                    int(row["source_pending_request_count"])
                    if row["source_pending_request_count"] is not None
                    else None
                ),
                "sourceHash": str(row["source_hash"] or "").strip() or None,
            }

        turn_rows = self._db.execute(
            "SELECT thread_id, turn_id, turn_json, is_active FROM session_v2_turns"
        ).fetchall()
        for row in turn_rows:
            thread_id = str(row["thread_id"] or "").strip()
            turn_id = str(row["turn_id"] or "").strip()
            if not thread_id or not turn_id:
                continue
            try:
                turn = json.loads(str(row["turn_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            if not isinstance(turn, dict):
                continue
            self._turns[thread_id][turn_id] = turn
            if int(row["is_active"] or 0) == 1:
                self._active_turn_by_thread[thread_id] = turn_id

        request_rows = self._db.execute(
            """
            SELECT
                request_id,
                raw_request_id_json,
                method,
                thread_id,
                turn_id,
                item_id,
                status,
                submission_kind,
                created_at_ms,
                submitted_at_ms,
                resolved_at_ms,
                payload_json
            FROM session_v2_pending_requests
            """
        ).fetchall()
        for row in request_rows:
            request_id = str(row["request_id"] or "").strip()
            thread_id = str(row["thread_id"] or "").strip()
            turn_id = self._optional_non_empty(row["turn_id"])
            raw_request_json = str(row["raw_request_id_json"] or "").strip()
            method = str(row["method"] or "").strip()
            if not request_id or not thread_id or not raw_request_json or not method:
                continue
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            record = {
                "requestId": request_id,
                "rawRequestIdJson": raw_request_json,
                "method": method,
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": str(row["item_id"] or "").strip() or None,
                "status": str(row["status"] or "pending"),
                "submissionKind": str(row["submission_kind"] or "").strip() or None,
                "createdAtMs": int(row["created_at_ms"] or 0),
                "submittedAtMs": int(row["submitted_at_ms"] or 0) or None,
                "resolvedAtMs": int(row["resolved_at_ms"] or 0) or None,
                "payload": payload,
            }
            self._pending_requests[request_id] = record
            if str(record.get("status") or "") in _PENDING_REQUEST_ACTIVE_STATUSES:
                self._pending_request_by_raw[(thread_id, raw_request_json)] = request_id
        for thread_id in self._turns.keys():
            self._touch_thread_state_locked(thread_id, self._now_ms())

    def _persist_event(self, event: dict[str, Any]) -> None:
        if self._db is None:
            return
        thread_id = str(event["threadId"])
        event_seq = int(event["eventSeq"])
        occurred_at_ms = int(event.get("occurredAtMs") or self._now_ms())
        event_json = json.dumps(event, ensure_ascii=True, sort_keys=True)
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_journal(thread_id, event_seq, occurred_at_ms, event_json)
            VALUES (?, ?, ?, ?)
            """,
            (thread_id, event_seq, occurred_at_ms, event_json),
        )
        self._db.commit()
        self._trim_db_journal(thread_id, now_ms=occurred_at_ms)

    def _persist_turn(self, thread_id: str, turn: dict[str, Any]) -> None:
        if self._db is None:
            return
        turn_id = str(turn.get("id") or "").strip()
        if not turn_id:
            return
        is_active = 1 if self._active_turn_by_thread.get(thread_id) == turn_id else 0
        now_ms = self._now_ms()
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_turns(thread_id, turn_id, status, turn_json, is_active, last_updated_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                turn_id,
                str(turn.get("status") or ""),
                json.dumps(turn, ensure_ascii=True, sort_keys=True),
                is_active,
                now_ms,
            ),
        )
        self._db.commit()

    def _persist_pending_request(self, record: dict[str, Any]) -> None:
        if self._db is None:
            return
        turn_id = self._optional_non_empty(record.get("turnId"))
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_pending_requests(
                request_id,
                raw_request_id_json,
                method,
                thread_id,
                turn_id,
                item_id,
                status,
                submission_kind,
                created_at_ms,
                submitted_at_ms,
                resolved_at_ms,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.get("requestId") or ""),
                str(record.get("rawRequestIdJson") or ""),
                str(record.get("method") or ""),
                str(record.get("threadId") or ""),
                turn_id,
                str(record.get("itemId") or "") or None,
                str(record.get("status") or "pending"),
                str(record.get("submissionKind") or "") or None,
                int(record.get("createdAtMs") or 0),
                int(record.get("submittedAtMs") or 0) or None,
                int(record.get("resolvedAtMs") or 0) or None,
                json.dumps(record.get("payload") or {}, ensure_ascii=True, sort_keys=True),
            ),
        )
        self._db.commit()

    def _persist_idempotency_record(self, action_type: str, key: str, record: dict[str, Any]) -> None:
        if self._db is None:
            return
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_idempotency(
                action_type,
                idempotency_key,
                payload_hash,
                response_json,
                response_hash,
                thread_id,
                turn_id,
                request_id,
                accepted_at_ms,
                journal_event_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_type,
                key,
                record["payload_hash"],
                record["response_json"],
                record["response_hash"],
                record.get("thread_id") or "",
                record.get("turn_id") or "",
                record.get("request_id") or "",
                int(record["accepted_at_ms"]),
                record.get("journal_event_seq"),
            ),
        )
        self._db.commit()

    def _persist_legacy_migration_marker(self, record: dict[str, Any]) -> None:
        if self._db is None:
            return
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_legacy_migrations(
                thread_id,
                migrated_at_ms,
                source_project_id,
                source_node_id,
                source_role,
                source_snapshot_version,
                source_item_count,
                source_pending_request_count,
                source_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.get("threadId") or ""),
                int(record.get("migratedAtMs") or self._now_ms()),
                record.get("sourceProjectId"),
                record.get("sourceNodeId"),
                record.get("sourceRole"),
                record.get("sourceSnapshotVersion"),
                record.get("sourceItemCount"),
                record.get("sourcePendingRequestCount"),
                record.get("sourceHash"),
            ),
        )
        self._db.commit()

    def _load_idempotency_from_db(self, action_type: str, key: str) -> dict[str, Any] | None:
        if self._db is None:
            return None
        row = self._db.execute(
            """
            SELECT payload_hash, response_json, response_hash, thread_id, turn_id, request_id, accepted_at_ms, journal_event_seq
            FROM session_v2_idempotency
            WHERE action_type = ? AND idempotency_key = ?
            """,
            (action_type, key),
        ).fetchone()
        if row is None:
            return None
        return {
            "payload_hash": str(row["payload_hash"]),
            "response_json": str(row["response_json"]),
            "response_hash": str(row["response_hash"]),
            "thread_id": str(row["thread_id"] or ""),
            "turn_id": str(row["turn_id"] or ""),
            "request_id": str(row["request_id"] or ""),
            "accepted_at_ms": int(row["accepted_at_ms"] or 0),
            "journal_event_seq": row["journal_event_seq"],
        }

    def _load_legacy_migration_marker_from_db(self, thread_id: str) -> dict[str, Any] | None:
        if self._db is None:
            return None
        row = self._db.execute(
            """
            SELECT
                thread_id,
                migrated_at_ms,
                source_project_id,
                source_node_id,
                source_role,
                source_snapshot_version,
                source_item_count,
                source_pending_request_count,
                source_hash
            FROM session_v2_legacy_migrations
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "threadId": str(row["thread_id"] or ""),
            "migratedAtMs": int(row["migrated_at_ms"] or 0),
            "sourceProjectId": str(row["source_project_id"] or "").strip() or None,
            "sourceNodeId": str(row["source_node_id"] or "").strip() or None,
            "sourceRole": str(row["source_role"] or "").strip() or None,
            "sourceSnapshotVersion": (
                int(row["source_snapshot_version"])
                if row["source_snapshot_version"] is not None
                else None
            ),
            "sourceItemCount": (
                int(row["source_item_count"])
                if row["source_item_count"] is not None
                else None
            ),
            "sourcePendingRequestCount": (
                int(row["source_pending_request_count"])
                if row["source_pending_request_count"] is not None
                else None
            ),
            "sourceHash": str(row["source_hash"] or "").strip() or None,
        }

    def _trim_memory_journal(self, thread_id: str, *, now_ms: int) -> None:
        events = self._journal.get(thread_id)
        if not events:
            return
        min_occurred_ms = int(now_ms) - self._retention_window_ms
        while len(events) > self._retention_max_events:
            oldest = events[0]
            oldest_occurred_ms = int(oldest.get("occurredAtMs") or 0)
            if oldest_occurred_ms >= min_occurred_ms:
                break
            del events[0]

    def _trim_db_journal(self, thread_id: str, *, now_ms: int) -> None:
        if self._db is None:
            return
        row = self._db.execute(
            "SELECT COUNT(1) AS count FROM session_v2_journal WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        total = int(row["count"] or 0) if row is not None else 0
        overflow = total - self._retention_max_events
        if overflow <= 0:
            return
        min_occurred_ms = int(now_ms) - self._retention_window_ms
        self._db.execute(
            """
            DELETE FROM session_v2_journal
            WHERE thread_id = ?
              AND event_seq IN (
                SELECT event_seq
                FROM session_v2_journal
                WHERE thread_id = ?
                  AND occurred_at_ms < ?
                ORDER BY event_seq ASC
                LIMIT ?
              )
            """,
            (thread_id, thread_id, min_occurred_ms, overflow),
        )
        self._db.commit()

    def _read_journal_events_locked(self, thread_id: str, *, after_event_seq: int) -> list[dict[str, Any]]:
        if self._db is None:
            source = self._journal.get(thread_id, [])
            return [dict(event) for event in source if int(event.get("eventSeq") or 0) > after_event_seq]
        rows = self._db.execute(
            """
            SELECT event_json
            FROM session_v2_journal
            WHERE thread_id = ? AND event_seq > ?
            ORDER BY event_seq ASC
            """,
            (thread_id, int(after_event_seq)),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(str(row["event_json"] or "{}"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def _find_event_by_method_and_turn_locked(
        self,
        *,
        thread_id: str,
        method: str,
        turn_id: str,
    ) -> dict[str, Any] | None:
        events = self._read_journal_events_locked(thread_id, after_event_seq=0)
        for event in reversed(events):
            if str(event.get("method") or "") != method:
                continue
            event_turn_id = str(event.get("turnId") or "").strip()
            if event_turn_id == turn_id:
                return event
            params = event.get("params")
            nested_turn = params.get("turn") if isinstance(params, dict) else None
            nested_turn_id = str(nested_turn.get("id") or "").strip() if isinstance(nested_turn, dict) else ""
            if nested_turn_id == turn_id:
                return event
        return None

    def _assert_cursor_available(self, *, thread_id: str, cursor_value: int) -> None:
        first_seq, last_seq = self._read_first_last_seq(thread_id)
        if first_seq is None or last_seq is None:
            if cursor_value == 0:
                return
            raise SessionCoreError(
                code="ERR_CURSOR_INVALID",
                message="Cursor references an empty stream.",
                status_code=409,
                details={"threadId": thread_id, "cursor": cursor_value},
            )
        if cursor_value > last_seq:
            raise SessionCoreError(
                code="ERR_CURSOR_INVALID",
                message="Cursor is ahead of stream tail.",
                status_code=409,
                details={"threadId": thread_id, "cursor": cursor_value, "lastEventSeq": last_seq},
            )
        if cursor_value < first_seq - 1:
            self._cursor_expired_count += 1
            snapshot_pointer = self._snapshot_pointer(thread_id=thread_id, last_event_seq=last_seq)
            raise SessionCoreError(
                code="ERR_CURSOR_EXPIRED",
                message="Cursor is outside replay retention window.",
                status_code=409,
                details={
                    "threadId": thread_id,
                    "cursor": cursor_value,
                    "firstRetainedEventSeq": first_seq,
                    "lastEventSeq": last_seq,
                    "snapshotPointer": snapshot_pointer,
                },
            )

    def _read_first_last_seq(self, thread_id: str) -> tuple[int | None, int | None]:
        if self._db is None:
            events = self._journal.get(thread_id, [])
            if not events:
                return None, None
            return int(events[0]["eventSeq"]), int(events[-1]["eventSeq"])
        row = self._db.execute(
            """
            SELECT MIN(event_seq) AS first_seq, MAX(event_seq) AS last_seq
            FROM session_v2_journal
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
        if row is None or row["first_seq"] is None or row["last_seq"] is None:
            return None, None
        return int(row["first_seq"]), int(row["last_seq"])

    def _maybe_update_snapshot(self, *, thread_id: str, event_seq: int, now_ms: int, tier: str) -> int | None:
        current_version = int(self._snapshot_versions.get(thread_id) or 0)
        last_ms = int(self._snapshot_last_ms.get(thread_id) or 0)
        if tier == "tier0":
            self._tier0_events_since_snapshot[thread_id] += 1
        tier0_count = int(self._tier0_events_since_snapshot.get(thread_id) or 0)
        should_bump = (
            last_ms == 0
            or (now_ms - last_ms) >= _SNAPSHOT_TIME_INTERVAL_MS
            or tier0_count >= _SNAPSHOT_TIER0_EVENT_INTERVAL
        )
        if not should_bump:
            return current_version or None

        current_version += 1
        self._snapshot_versions[thread_id] = current_version
        self._snapshot_last_ms[thread_id] = now_ms
        self._snapshot_last_event_seq[thread_id] = event_seq
        self._tier0_events_since_snapshot[thread_id] = 0
        snapshot_payload = self._build_snapshot_payload(
            thread_id=thread_id,
            snapshot_version=current_version,
            last_event_seq=event_seq,
            updated_at_ms=now_ms,
        )
        self._snapshot_payloads[thread_id] = snapshot_payload
        self._persist_snapshot(snapshot_payload)
        return current_version

    def _fanout_event(self, event: dict[str, Any]) -> None:
        thread_id = str(event.get("threadId") or "")
        tier = str(event.get("tier") or "tier2")
        to_remove: list[str] = []
        matched_subscriber_count = 0
        max_queue_depth = 0
        for subscriber_id, subscriber in self._subscribers.items():
            if subscriber.thread_id != thread_id:
                continue
            matched_subscriber_count += 1
            try:
                subscriber.events.put_nowait(dict(event))
                max_queue_depth = max(max_queue_depth, subscriber.events.qsize())
            except queue.Full:
                self._lagged_reset_count += 1
                if tier == "tier2":
                    self._drop_counts_by_tier[tier] += 1
                subscriber.lagged = True
                drained = self._drain_queue(subscriber.events)
                skipped = max(1, drained + 1)
                try:
                    subscriber.events.put_nowait(
                        {
                            "__control": "lagged",
                            "threadId": thread_id,
                            "skipped": skipped,
                        }
                    )
                except queue.Full:
                    pass
                logger.warning(
                    "session_core_v2 lagged subscriber reset",
                    extra={
                        "threadId": thread_id,
                        "eventSeq": event.get("eventSeq"),
                        "errorCode": "ERR_SUBSCRIBER_LAGGED",
                        "tier": tier,
                        "skipped": skipped,
                    },
                )
                to_remove.append(subscriber_id)
        for subscriber_id in to_remove:
            self._subscribers.pop(subscriber_id, None)
        method = str(event.get("method") or "")
        if method in _STREAM_TRACE_METHODS:
            logger.info(
                "session_core_v2 stream fanout",
                extra={
                    "threadId": thread_id,
                    "eventSeq": event.get("eventSeq"),
                    "method": method,
                    "matchedSubscriberCount": matched_subscriber_count,
                    "subscriberQueueDepthMax": max_queue_depth,
                    "laggedSubscriberRemoved": len(to_remove),
                },
            )

    def _subscriber_count_for_thread_locked(self, thread_id: str) -> int:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id:
            return 0
        count = 0
        for subscriber in self._subscribers.values():
            if subscriber.thread_id == normalized_thread_id:
                count += 1
        return count

    @staticmethod
    def _drain_queue(event_queue: queue.Queue[dict[str, Any]]) -> int:
        drained = 0
        while True:
            try:
                event_queue.get_nowait()
                drained += 1
            except queue.Empty:
                return drained

    def _build_snapshot_payload(
        self,
        *,
        thread_id: str,
        snapshot_version: int,
        last_event_seq: int,
        updated_at_ms: int,
    ) -> dict[str, Any]:
        thread_state = dict(self._thread_state.get(thread_id) or {})
        if not thread_state:
            thread_state = {"id": thread_id}
        thread_state["id"] = thread_id
        thread_state["activeTurnId"] = self._active_turn_by_thread.get(thread_id)
        thread_state["updatedAtMs"] = int(updated_at_ms)

        turn_index: dict[str, dict[str, Any]] = {}
        item_index: dict[str, list[dict[str, Any]]] = {}
        for turn_id, turn in self._turns.get(thread_id, {}).items():
            if not isinstance(turn, dict):
                continue
            turn_index[turn_id] = {
                "status": turn.get("status"),
                "lastCodexStatus": turn.get("lastCodexStatus"),
                "startedAtMs": turn.get("startedAtMs"),
                "completedAtMs": turn.get("completedAtMs"),
                "error": turn.get("error"),
            }
            raw_items = turn.get("items")
            serialized_items: list[dict[str, Any]] = []
            if isinstance(raw_items, list):
                for raw_item in raw_items:
                    if isinstance(raw_item, dict):
                        serialized_items.append(dict(raw_item))
            item_index[turn_id] = serialized_items

        pending_request_index: dict[str, dict[str, Any]] = {}
        for request_id, request_record in self._pending_requests.items():
            if str(request_record.get("threadId") or "").strip() != thread_id:
                continue
            pending_request_index[request_id] = self._pending_request_public(request_record)

        return {
            "snapshotVersion": int(snapshot_version),
            "thread": thread_state,
            "turnIndex": turn_index,
            "itemIndex": item_index,
            "pendingRequestIndex": pending_request_index,
            "lastEventSeq": int(last_event_seq),
            "updatedAtMs": int(updated_at_ms),
        }

    def _persist_snapshot(self, snapshot_payload: dict[str, Any]) -> None:
        if self._db is None:
            return
        thread = snapshot_payload.get("thread")
        if not isinstance(thread, dict):
            return
        thread_id = str(thread.get("id") or "").strip()
        if not thread_id:
            return
        self._db.execute(
            """
            INSERT OR REPLACE INTO session_v2_snapshots(
                thread_id,
                snapshot_version,
                last_event_seq,
                updated_at_ms,
                snapshot_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                int(snapshot_payload.get("snapshotVersion") or 0),
                int(snapshot_payload.get("lastEventSeq") or 0),
                int(snapshot_payload.get("updatedAtMs") or 0),
                json.dumps(snapshot_payload, ensure_ascii=True, sort_keys=True),
            ),
        )
        self._db.commit()

    def _snapshot_pointer(self, *, thread_id: str, last_event_seq: int) -> dict[str, Any]:
        payload = self._snapshot_payloads.get(thread_id)
        if isinstance(payload, dict):
            pointer_last_event_seq = int(payload.get("lastEventSeq") or last_event_seq)
            return {
                "snapshotVersion": int(payload.get("snapshotVersion") or 0),
                "lastEventSeq": pointer_last_event_seq,
                "updatedAtMs": int(payload.get("updatedAtMs") or 0),
            }
        return {
            "snapshotVersion": int(self._snapshot_versions.get(thread_id) or 0),
            "lastEventSeq": int(last_event_seq),
            "updatedAtMs": int(self._snapshot_last_ms.get(thread_id) or 0),
        }

    def _touch_thread_state_locked(self, thread_id: str, now_ms: int) -> None:
        state = dict(self._thread_state.get(thread_id) or {})
        state["id"] = thread_id
        state["activeTurnId"] = self._active_turn_by_thread.get(thread_id)
        state["updatedAtMs"] = int(now_ms)
        self._thread_state[thread_id] = state

    def _record_thread_state_from_notification(self, *, thread_id: str, method: str, params: dict[str, Any]) -> None:
        if not method.startswith("thread/"):
            return
        now_ms = self._now_ms()
        with self._lock:
            state = dict(self._thread_state.get(thread_id) or {})
            state["id"] = thread_id
            if method == "thread/status/changed":
                state["status"] = params.get("status")
            elif method == "thread/closed":
                state["status"] = {"type": "notLoaded"}
            elif method == "thread/started":
                if "status" not in state:
                    state["status"] = {"type": "idle"}
            state["activeTurnId"] = self._active_turn_by_thread.get(thread_id)
            state["updatedAtMs"] = now_ms
            self._thread_state[thread_id] = state

    @staticmethod
    def _resolve_event_tier(method: str) -> str:
        if method in _TIER0_METHODS:
            return "tier0"
        if method in _TIER1_METHODS:
            return "tier1"
        return "tier2"

    @staticmethod
    def _extract_thread_id(params: dict[str, Any]) -> str:
        value = params.get("threadId")
        if isinstance(value, str) and value.strip():
            return value.strip()
        nested = params.get("thread")
        if isinstance(nested, dict):
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                return nested_id.strip()
        return ""

    @staticmethod
    def _extract_turn_id(params: dict[str, Any]) -> str | None:
        value = params.get("turnId")
        if isinstance(value, str) and value.strip():
            return value.strip()
        nested = params.get("turn")
        if isinstance(nested, dict):
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                return nested_id.strip()
        return None

    @staticmethod
    def _serialize_raw_request_id(raw_request_id: Any) -> str:
        try:
            return json.dumps(raw_request_id, ensure_ascii=True, sort_keys=True)
        except TypeError as exc:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="Server request id is not JSON serializable.",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc

    @staticmethod
    def _deserialize_raw_request_id(raw_request_id_json: str) -> Any:
        try:
            return json.loads(raw_request_id_json)
        except json.JSONDecodeError as exc:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="Server request id payload is malformed.",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc

    @staticmethod
    def _pending_request_public(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "requestId": str(record.get("requestId") or ""),
            "method": str(record.get("method") or ""),
            "threadId": str(record.get("threadId") or ""),
            "turnId": RuntimeStoreV2._optional_non_empty(record.get("turnId")),
            "itemId": str(record.get("itemId") or "") or None,
            "status": str(record.get("status") or "pending"),
            "createdAtMs": int(record.get("createdAtMs") or 0),
            "submittedAtMs": int(record.get("submittedAtMs") or 0) or None,
            "resolvedAtMs": int(record.get("resolvedAtMs") or 0) or None,
            "payload": dict(record.get("payload") or {}),
        }

    def _append_pending_request_event_locked(self, *, method: str, record: dict[str, Any]) -> dict[str, Any]:
        public_record = self._pending_request_public(record)
        return self.append_event(
            thread_id=public_record["threadId"],
            method=method,
            params={"request": public_record},
            turn_id=public_record["turnId"],
            source="journal",
            replayable=True,
            tier="tier0",
        )

    def _resume_turn_if_no_unresolved_requests(self, *, thread_id: str, turn_id: str) -> None:
        unresolved = False
        for record in self._pending_requests.values():
            if str(record.get("threadId") or "").strip() != thread_id:
                continue
            if str(record.get("turnId") or "").strip() != turn_id:
                continue
            if str(record.get("status") or "") in _PENDING_REQUEST_ACTIVE_STATUSES:
                unresolved = True
                break
        if unresolved:
            return
        turn = self._turns.get(thread_id, {}).get(turn_id)
        if not isinstance(turn, dict):
            return
        if str(turn.get("status") or "") != "waitingUserInput":
            return
        try:
            self.transition_turn(
                thread_id=thread_id,
                turn_id=turn_id,
                next_status="inProgress",
                allow_same=True,
            )
        except SessionCoreError:
            logger.debug("session_core_v2 failed to resume waiting turn", exc_info=True)

    @staticmethod
    def _normalize_non_empty(value: str, field_name: str) -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
        raise SessionCoreError(
            code="ERR_INTERNAL",
            message=f"{field_name} cannot be empty.",
            status_code=500,
            details={"field": field_name},
        )

    @staticmethod
    def _optional_non_empty(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized:
            return normalized
        return None

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    @staticmethod
    def _copy_turn(turn: dict[str, Any]) -> dict[str, Any]:
        copied = dict(turn)
        items = copied.get("items")
        if isinstance(items, list):
            copied["items"] = [dict(item) if isinstance(item, dict) else item for item in items]
        return copied

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
