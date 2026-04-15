from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

from backend.config.app_config import get_thread_actor_mode
from backend.conversation.domain import events as event_types
from backend.conversation.domain.types_v3 import (
    ConversationItemV3,
    ThreadActorModeV3,
    ThreadRoleV3,
    ThreadSnapshotV3,
    UserInputAnswerV3,
    copy_snapshot_v3,
    normalize_user_input_answer_v3,
)
from backend.conversation.projector.thread_event_projector_runtime_v3 import (
    apply_lifecycle_v3,
    apply_raw_event_v3,
    apply_resolved_user_input_v3,
    finalize_turn_v3,
    patch_item_v3,
    upsert_item_v3,
)
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.errors.app_errors import (
    AskIdempotencyPayloadConflict,
    ChatBackendUnavailable,
    ChatTurnAlreadyActive,
    InvalidRequest,
)
from backend.storage.file_utils import iso_now, new_id

logger = logging.getLogger(__name__)

_ASK_READ_ONLY_POLICY_ERROR = (
    "Ask lane is read-only. File-change output is not allowed in ask turns."
)

_COMPACTION_WINDOW_MS_DEFAULT = 50
_COMPACTION_WINDOW_MS_MIN = 40
_COMPACTION_WINDOW_MS_MAX = 60
_COMPACTION_MAX_BATCH_SIZE_DEFAULT = 64

_COMPACTION_MERGE_SAFE_METHODS = {
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryDelta",
    "item/reasoning/detailDelta",
    "item/commandExecution/outputDelta",
    "item/fileChange/outputDelta",
}

_COMPACTION_BOUNDARY_METHODS = {
    "item/completed",
    "turn/completed",
    "item/tool/requestUserInput",
    "serverRequest/resolved",
    "thread/status/changed",
}

_FILE_CHANGE_OUTPUT_DELTA_METHOD = "item/fileChange/outputDelta"

_ASK_START_IDEMPOTENCY_CACHE_PREFIX = "ask_start_turn_v1:"
_ASK_START_IDEMPOTENCY_TTL_MS = 20 * 60 * 1000
_ASK_START_IDEMPOTENCY_MAX_ENTRIES = 256


def _normalize_optional_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _coerce_nonnegative_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


class _RawEventCompactorV3:
    def __init__(
        self,
        *,
        default_thread_id: str | None,
        default_turn_id: str | None,
        window_ms: int,
        max_batch_size: int,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self._default_thread_id = _normalize_optional_id(default_thread_id)
        self._default_turn_id = _normalize_optional_id(default_turn_id)
        self._window_ms = max(1, int(window_ms))
        self._max_batch_size = max(1, int(max_batch_size))
        self._now_ms = now_ms if callable(now_ms) else lambda: int(time.monotonic() * 1000)
        self._pending: list[dict[str, Any]] = []
        self._batch_started_ms: int | None = None

    def push(self, raw_event: dict[str, Any]) -> list[dict[str, Any]]:
        method = str(raw_event.get("method") or "").strip()
        if not method:
            return []

        ready = self._flush_due_to_window_fail_open()
        if method in _COMPACTION_BOUNDARY_METHODS:
            ready.extend(self.flush())
            ready.append(copy.deepcopy(raw_event))
            return ready

        if method not in _COMPACTION_MERGE_SAFE_METHODS:
            ready.extend(self.flush())
            ready.append(copy.deepcopy(raw_event))
            return ready

        candidate = copy.deepcopy(raw_event)
        if not self._is_merge_payload_compatible(candidate):
            ready.extend(self.flush())
            ready.append(candidate)
            return ready

        if not self._try_merge_into_tail(candidate):
            self._append_pending(candidate)

        if len(self._pending) >= self._max_batch_size:
            ready.extend(self.flush())
        return ready

    def flush(self) -> list[dict[str, Any]]:
        if not self._pending:
            return []
        out = self._pending
        self._pending = []
        self._batch_started_ms = None
        return out

    def _resolve_thread_id(self, raw_event: dict[str, Any]) -> str | None:
        return _normalize_optional_id(raw_event.get("thread_id") or raw_event.get("threadId") or self._default_thread_id)

    def _resolve_turn_id(self, raw_event: dict[str, Any]) -> str | None:
        return _normalize_optional_id(raw_event.get("turn_id") or raw_event.get("turnId") or self._default_turn_id)

    def _resolve_item_id(self, raw_event: dict[str, Any]) -> str | None:
        return _normalize_optional_id(raw_event.get("item_id") or raw_event.get("itemId"))

    def _merge_key(self, raw_event: dict[str, Any]) -> tuple[str, str, str, str] | None:
        method = str(raw_event.get("method") or "").strip()
        if method not in _COMPACTION_MERGE_SAFE_METHODS:
            return None
        thread_id = self._resolve_thread_id(raw_event)
        turn_id = self._resolve_turn_id(raw_event)
        item_id = self._resolve_item_id(raw_event)
        if not thread_id or not turn_id or not item_id:
            return None
        return (thread_id, turn_id, item_id, method)

    @staticmethod
    def _params_for_event(raw_event: dict[str, Any]) -> dict[str, Any] | None:
        params = raw_event.get("params", {})
        return params if isinstance(params, dict) else None

    def _is_merge_payload_compatible(self, raw_event: dict[str, Any]) -> bool:
        method = str(raw_event.get("method") or "").strip()
        if self._merge_key(raw_event) is None:
            return False
        params = self._params_for_event(raw_event)
        if params is None:
            return False
        allowed_fields = {"delta", "files"} if method == _FILE_CHANGE_OUTPUT_DELTA_METHOD else {"delta"}
        return all(str(key) in allowed_fields for key in params.keys())

    def _try_merge_into_tail(self, candidate: dict[str, Any]) -> bool:
        if not self._pending:
            return False
        tail = self._pending[-1]
        if self._merge_key(tail) != self._merge_key(candidate):
            return False
        if not self._is_merge_payload_compatible(tail):
            return False

        method = str(candidate.get("method") or "").strip()
        tail_params = self._params_for_event(tail)
        candidate_params = self._params_for_event(candidate)
        if tail_params is None or candidate_params is None:
            return False

        tail_delta = str(tail_params.get("delta") or "")
        candidate_delta = str(candidate_params.get("delta") or "")
        tail_params["delta"] = tail_delta + candidate_delta

        if method == _FILE_CHANGE_OUTPUT_DELTA_METHOD:
            candidate_files = candidate_params.get("files")
            if isinstance(candidate_files, list) and candidate_files:
                existing_files = tail_params.get("files")
                existing_files_list = list(existing_files) if isinstance(existing_files, list) else []
                existing_files_list.extend(copy.deepcopy(candidate_files))
                tail_params["files"] = existing_files_list
        return True

    def _append_pending(self, raw_event: dict[str, Any]) -> None:
        if not self._pending:
            started_at = self._safe_now_ms()
            self._batch_started_ms = started_at if started_at is not None else 0
        self._pending.append(raw_event)

    def _flush_due_to_window_fail_open(self) -> list[dict[str, Any]]:
        if not self._pending:
            return []
        now_ms = self._safe_now_ms()
        if now_ms is None:
            return self.flush()
        started_ms = self._batch_started_ms if self._batch_started_ms is not None else now_ms
        if now_ms - started_ms >= self._window_ms:
            return self.flush()
        return []

    def _safe_now_ms(self) -> int | None:
        try:
            return int(self._now_ms())
        except Exception:
            logger.debug("Raw-event compaction clock failed; forcing fail-open flush.", exc_info=True)
            return None


class ThreadRuntimeServiceV3:
    def __init__(
        self,
        *,
        storage: Any,
        tree_service: Any,
        chat_service: Any,
        codex_client: Any,
        query_service: ThreadQueryServiceV3,
        request_ledger_service: RequestLedgerServiceV3,
        chat_timeout: int,
        max_message_chars: int = 10000,
        ask_rollout_metrics_service: Any | None = None,
        coalescing_window_ms: int = _COMPACTION_WINDOW_MS_DEFAULT,
        coalescing_max_batch_size: int = _COMPACTION_MAX_BATCH_SIZE_DEFAULT,
        thread_actor_mode: ThreadActorModeV3 | str | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._chat_service = chat_service
        self._codex_client = codex_client
        self._query_service = query_service
        self._request_ledger_service = request_ledger_service
        self._chat_timeout = int(chat_timeout)
        self._max_message_chars = int(max_message_chars)
        self._ask_rollout_metrics_service = ask_rollout_metrics_service
        self._coalescing_window_ms = max(
            _COMPACTION_WINDOW_MS_MIN,
            min(_COMPACTION_WINDOW_MS_MAX, int(coalescing_window_ms)),
        )
        self._coalescing_max_batch_size = max(1, int(coalescing_max_batch_size))
        resolved_mode = str(thread_actor_mode or get_thread_actor_mode()).strip().lower()
        if resolved_mode not in {"off", "shadow", "on"}:
            resolved_mode = "off"
        self._thread_actor_mode: ThreadActorModeV3 = resolved_mode  # type: ignore[assignment]

    def _persist_mutation_v3(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        snapshot: ThreadSnapshotV3,
        events: list[dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        return self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            snapshot,
            events,
        )

    @staticmethod
    def _extract_ask_idempotency_key(metadata: dict[str, Any] | None) -> str | None:
        if not isinstance(metadata, dict):
            return None
        key = str(metadata.get("idempotencyKey") or "").strip()
        return key or None

    @staticmethod
    def _ask_start_idempotency_cache_key(thread_id: str, idempotency_key: str) -> str:
        return f"{_ASK_START_IDEMPOTENCY_CACHE_PREFIX}{thread_id}:{idempotency_key}"

    @staticmethod
    def _ask_start_text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _now_epoch_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _build_ask_idempotency_entry(
        *,
        thread_id: str,
        turn_id: str,
        text_hash: str,
        response_payload: dict[str, Any],
        now_ms: int,
    ) -> dict[str, Any]:
        return {
            "threadId": thread_id,
            "turnId": turn_id,
            "textHash": text_hash,
            "response": copy.deepcopy(response_payload),
            "createdAtMs": int(now_ms),
            "lastSeenAtMs": int(now_ms),
        }

    def _prune_ask_start_idempotency_cache(
        self,
        mutation_cache: dict[str, Any],
        *,
        now_ms: int,
    ) -> bool:
        changed = False
        retained: list[tuple[str, int]] = []
        for cache_key in list(mutation_cache.keys()):
            if not str(cache_key).startswith(_ASK_START_IDEMPOTENCY_CACHE_PREFIX):
                continue
            entry = mutation_cache.get(cache_key)
            if not isinstance(entry, dict):
                mutation_cache.pop(cache_key, None)
                changed = True
                continue
            created_at_ms = _coerce_nonnegative_ms(entry.get("createdAtMs"))
            last_seen_at_ms = _coerce_nonnegative_ms(entry.get("lastSeenAtMs"))
            anchor_ms = max(created_at_ms, last_seen_at_ms)
            if anchor_ms <= 0:
                mutation_cache.pop(cache_key, None)
                changed = True
                continue
            if now_ms - anchor_ms > _ASK_START_IDEMPOTENCY_TTL_MS:
                mutation_cache.pop(cache_key, None)
                changed = True
                continue
            retained.append((str(cache_key), anchor_ms))

        overflow = len(retained) - _ASK_START_IDEMPOTENCY_MAX_ENTRIES
        if overflow > 0:
            retained.sort(key=lambda item: (item[1], item[0]))
            for cache_key, _ in retained[:overflow]:
                mutation_cache.pop(cache_key, None)
                changed = True
        return changed

    def _load_workflow_state_locked(self, project_id: str, node_id: str) -> dict[str, Any]:
        state = self._storage.workflow_state_store.read_state(project_id, node_id)
        if isinstance(state, dict):
            return state
        return self._storage.workflow_state_store.default_state(node_id)

    def _replay_ask_start_if_idempotent_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        idempotency_key: str,
        text_hash: str,
        now_ms: int,
    ) -> dict[str, Any] | None:
        state = self._load_workflow_state_locked(project_id, node_id)
        mutation_cache = state.get("mutationCache")
        if not isinstance(mutation_cache, dict):
            mutation_cache = {}
        changed = self._prune_ask_start_idempotency_cache(mutation_cache, now_ms=now_ms)
        cache_key = self._ask_start_idempotency_cache_key(thread_id, idempotency_key)
        cached = mutation_cache.get(cache_key)
        if not isinstance(cached, dict):
            if changed:
                state["mutationCache"] = mutation_cache
                self._storage.workflow_state_store.write_state(project_id, node_id, state)
            return None

        cached_text_hash = str(cached.get("textHash") or "").strip()
        if not cached_text_hash:
            mutation_cache.pop(cache_key, None)
            state["mutationCache"] = mutation_cache
            self._storage.workflow_state_store.write_state(project_id, node_id, state)
            return None
        if cached_text_hash != text_hash:
            raise AskIdempotencyPayloadConflict()

        response_payload = cached.get("response")
        if not isinstance(response_payload, dict):
            mutation_cache.pop(cache_key, None)
            state["mutationCache"] = mutation_cache
            self._storage.workflow_state_store.write_state(project_id, node_id, state)
            return None

        cached["lastSeenAtMs"] = now_ms
        mutation_cache[cache_key] = cached
        state["mutationCache"] = mutation_cache
        self._storage.workflow_state_store.write_state(project_id, node_id, state)
        return copy.deepcopy(response_payload)

    def _store_ask_start_idempotency_locked(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        idempotency_key: str,
        text_hash: str,
        response_payload: dict[str, Any],
        now_ms: int,
    ) -> None:
        state = self._load_workflow_state_locked(project_id, node_id)
        mutation_cache = state.get("mutationCache")
        if not isinstance(mutation_cache, dict):
            mutation_cache = {}
        self._prune_ask_start_idempotency_cache(mutation_cache, now_ms=now_ms)
        cache_key = self._ask_start_idempotency_cache_key(thread_id, idempotency_key)
        mutation_cache[cache_key] = self._build_ask_idempotency_entry(
            thread_id=thread_id,
            turn_id=str(response_payload.get("turnId") or ""),
            text_hash=text_hash,
            response_payload=response_payload,
            now_ms=now_ms,
        )
        self._prune_ask_start_idempotency_cache(mutation_cache, now_ms=now_ms)
        state["mutationCache"] = mutation_cache
        self._storage.workflow_state_store.write_state(project_id, node_id, state)

    def _create_start_turn_payload(
        self,
        *,
        snapshot: ThreadSnapshotV3,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        cleaned_text: str,
    ) -> tuple[dict[str, Any], str, str]:
        if snapshot.get("activeTurnId"):
            raise ChatTurnAlreadyActive()
        thread_id = str(snapshot.get("threadId") or "").strip()
        if not thread_id:
            raise ChatBackendUnavailable("V3 thread bootstrap did not return a thread id.")
        turn_id = new_id("turn")
        user_item = self._build_local_user_item(
            snapshot=snapshot,
            thread_id=thread_id,
            turn_id=turn_id,
            text=cleaned_text,
        )
        updated = self.begin_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            origin="interactive",
            created_items=[user_item],
            turn_id=turn_id,
        )
        payload = {
            "accepted": True,
            "threadId": thread_id,
            "turnId": turn_id,
            "snapshotVersion": updated["snapshotVersion"],
            "createdItems": [user_item],
        }
        return payload, thread_id, turn_id

    def _start_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        turn_id: str,
        input_text: str,
    ) -> None:
        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "thread_role": thread_role,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "input_text": input_text,
            },
            daemon=True,
        ).start()

    def start_turn(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._chat_service._validate_thread_access(project_id, node_id, thread_role)
        self._chat_service._check_thread_writable(project_id, node_id, thread_role)
        cleaned = str(text or "").strip()
        if not cleaned:
            raise InvalidRequest("Message text is required.")
        if len(cleaned) > self._max_message_chars:
            raise InvalidRequest(
                f"Message text exceeds {self._max_message_chars} character limit."
            )
        if thread_role == "audit":
            self._chat_service._maybe_start_local_review_for_audit_write(project_id, node_id)

        ask_idempotency_key = (
            self._extract_ask_idempotency_key(metadata)
            if thread_role == "ask_planning"
            else None
        )
        if ask_idempotency_key:
            now_ms = self._now_epoch_ms()
            text_hash = self._ask_start_text_hash(cleaned)
            with self._storage.project_lock(project_id):
                snapshot = self._query_service.get_thread_snapshot(project_id, node_id, thread_role)
                thread_id = str(snapshot.get("threadId") or "").strip()
                if not thread_id:
                    raise ChatBackendUnavailable("V3 thread bootstrap did not return a thread id.")
                replay = self._replay_ask_start_if_idempotent_locked(
                    project_id=project_id,
                    node_id=node_id,
                    thread_id=thread_id,
                    idempotency_key=ask_idempotency_key,
                    text_hash=text_hash,
                    now_ms=now_ms,
                )
                if replay is not None:
                    return replay
                payload, thread_id, turn_id = self._create_start_turn_payload(
                    snapshot=snapshot,
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    cleaned_text=cleaned,
                )
                self._store_ask_start_idempotency_locked(
                    project_id=project_id,
                    node_id=node_id,
                    thread_id=thread_id,
                    idempotency_key=ask_idempotency_key,
                    text_hash=text_hash,
                    response_payload=payload,
                    now_ms=now_ms,
                )
            self._start_background_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                thread_id=thread_id,
                turn_id=turn_id,
                input_text=cleaned,
            )
            return payload

        snapshot = self._query_service.get_thread_snapshot(project_id, node_id, thread_role)
        payload, thread_id, turn_id = self._create_start_turn_payload(
            snapshot=snapshot,
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            cleaned_text=cleaned,
        )
        self._start_background_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            thread_id=thread_id,
            turn_id=turn_id,
            input_text=cleaned,
        )
        return payload

    def begin_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        origin: str,
        created_items: list[ConversationItemV3],
        turn_id: str | None = None,
    ) -> ThreadSnapshotV3:
        del origin
        snapshot = self._query_service.get_thread_snapshot(project_id, node_id, thread_role)
        if snapshot.get("activeTurnId"):
            raise ChatTurnAlreadyActive()
        resolved_turn_id = str(turn_id or new_id("turn"))
        thread_id = str(snapshot.get("threadId") or "").strip() or None
        updated = copy_snapshot_v3(snapshot)
        events: list[dict[str, Any]] = []
        for item in created_items:
            normalized = dict(item)
            normalized["threadId"] = thread_id or str(item.get("threadId") or "")
            normalized["turnId"] = resolved_turn_id
            updated, item_events = upsert_item_v3(updated, normalized)  # type: ignore[arg-type]
            events.extend(item_events)
        updated, lifecycle_events = apply_lifecycle_v3(
            updated,
            state=event_types.TURN_STARTED,
            processing_state="running",
            active_turn_id=resolved_turn_id,
        )
        events.extend(lifecycle_events)
        persisted, _ = self._persist_mutation_v3(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=updated,
            events=events,
        )
        self._chat_service.register_external_live_turn(
            project_id,
            node_id,
            thread_role,
            resolved_turn_id,
        )
        return persisted

    def complete_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        turn_id: str,
        outcome: str,
        error_item: ConversationItemV3 | None = None,
    ) -> ThreadSnapshotV3:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, events = finalize_turn_v3(
            snapshot,
            turn_id=turn_id,
            outcome=outcome,
            error_item=error_item,
        )

        persisted, _ = self._persist_mutation_v3(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=updated,
            events=events,
        )
        if outcome == "waiting_user_input":
            return persisted
        self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
        return persisted

    def resolve_user_input(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        pending = self._find_pending_request(snapshot, request_id)
        if pending is None:
            raise InvalidRequest(f"Unknown user-input request {request_id!r}.")
        normalized_answers = self._normalize_answers(answers)
        submitted_at = iso_now()
        updated = self._request_ledger_service.submit_answers(
            snapshot,
            request_id=request_id,
            answers=normalized_answers,
        )
        updated, submit_events = patch_item_v3(
            updated,
            str(pending.get("itemId") or ""),
            {
                "kind": "userInput",
                "answersReplace": normalized_answers,
                "status": "answer_submitted",
                "updatedAt": submitted_at,
            },
        )
        self._persist_mutation_v3(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=updated,
            events=submit_events,
        )

        rpc_answers = {str(answer["questionId"]): answer.get("value") for answer in normalized_answers}
        record = self._codex_client.resolve_runtime_request_user_input(
            request_id,
            answers=rpc_answers,
        )
        if record is None:
            raise InvalidRequest(f"Unknown runtime user-input request {request_id!r}.")

        resolved_at = iso_now()
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, resolved_events = apply_resolved_user_input_v3(
            snapshot,
            request_id=request_id,
            item_id=str(pending.get("itemId") or ""),
            answers=normalized_answers,
            resolved_at=resolved_at,
        )
        if (
            snapshot.get("processingState") == "waiting_user_input"
            and str(snapshot.get("activeTurnId") or "") == str(pending.get("turnId") or "")
        ):
            updated, lifecycle_events = apply_lifecycle_v3(
                updated,
                state=event_types.TURN_COMPLETED,
                processing_state="idle",
                active_turn_id=None,
            )
            resolved_events.extend(lifecycle_events)
        persisted, _ = self._persist_mutation_v3(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=updated,
            events=resolved_events,
        )
        if str(persisted.get("activeTurnId") or "") != str(pending.get("turnId") or ""):
            turn_id = str(pending.get("turnId") or "").strip()
            if turn_id:
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
        return {
            "requestId": request_id,
            "itemId": str(pending.get("itemId") or ""),
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": pending.get("turnId"),
            "status": "answer_submitted",
            "answers": normalized_answers,
            "submittedAt": submitted_at,
        }

    def upsert_system_message(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        item_id: str,
        turn_id: str | None,
        text: str,
        tone: str = "neutral",
        metadata: dict[str, Any] | None = None,
    ) -> ThreadSnapshotV3:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        now = iso_now()
        item: ConversationItemV3 = {
            "id": item_id,
            "kind": "message",
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": turn_id,
            "sequence": self._next_sequence(snapshot),
            "createdAt": now,
            "updatedAt": now,
            "status": "completed",
            "source": "backend",
            "tone": tone,  # type: ignore[typeddict-item]
            "metadata": dict(metadata or {}),
            "role": "system",
            "text": str(text or ""),
            "format": "markdown",
        }
        updated, events = upsert_item_v3(snapshot, item)
        persisted, _ = self._persist_mutation_v3(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=updated,
            events=events,
        )
        return persisted

    def stream_agent_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        turn_id: str,
        prompt: str,
        cwd: str | None,
        writable_roots: list[str] | None = None,
        sandbox_profile: str | None = None,
        output_schema: dict[str, Any] | None = None,
        timeout_sec: int | None = None,
        on_raw_event_applied: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        provisional_tool_calls: dict[str, dict[str, Any]] = {}
        final_turn_status = "completed"
        compactor = self._build_raw_event_compactor(thread_id=thread_id, turn_id=turn_id)

        def process_ready_raw_events(ready_raw_events: list[dict[str, Any]]) -> None:
            nonlocal final_turn_status
            final_turn_status = self._apply_raw_event_batch_v3(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                raw_events=ready_raw_events,
                provisional_tool_calls=provisional_tool_calls,
                apply_turn_completed_event=True,
                final_turn_status=final_turn_status,
            )

        def handle_raw_event(raw_event: dict[str, Any]) -> None:
            nonlocal final_turn_status
            method = str(raw_event.get("method") or "").strip()
            if not method:
                return
            if method == "item/tool/call":
                call_id = str(raw_event.get("call_id") or "").strip()
                if not call_id:
                    return
                params = raw_event.get("params", {})
                provisional_tool_calls[call_id] = {
                    "callId": call_id,
                    "toolName": str(params.get("tool_name") or params.get("toolName") or "").strip() or None
                    if isinstance(params, dict)
                    else None,
                    "arguments": params.get("arguments") if isinstance(params, dict) else {},
                    "threadId": str(raw_event.get("thread_id") or thread_id),
                    "turnId": str(raw_event.get("turn_id") or turn_id),
                    "createdAt": str(raw_event.get("received_at") or iso_now()),
                    "matched": False,
                }
                if callable(on_raw_event_applied):
                    try:
                        on_raw_event_applied(raw_event)
                    except Exception:
                        logger.debug(
                            "stream_agent_turn on_raw_event_applied callback failed for %s/%s",
                            project_id,
                            node_id,
                            exc_info=True,
                        )
                return
            ready_raw_events = compactor.push(raw_event)
            if ready_raw_events:
                process_ready_raw_events(ready_raw_events)

            if callable(on_raw_event_applied):
                try:
                    on_raw_event_applied(raw_event)
                except Exception:
                    logger.debug(
                        "stream_agent_turn on_raw_event_applied callback failed for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )

        try:
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(timeout_sec or self._chat_timeout),
                cwd=cwd,
                writable_roots=writable_roots,
                sandbox_profile=sandbox_profile,
                on_raw_event=handle_raw_event,
                output_schema=output_schema,
            )
            process_ready_raw_events(compactor.flush())
            returned_status = str(result.get("turn_status") or "").strip().lower()
            if returned_status:
                final_turn_status = returned_status
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            return {
                "result": result,
                "turnStatus": final_turn_status,
            }
        except Exception:
            process_ready_raw_events(compactor.flush())
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            raise

    @staticmethod
    def outcome_from_turn_status(turn_status: str | None) -> str:
        normalized = str(turn_status or "").strip().lower()
        if normalized in {"waiting_user_input", "waitingforuserinput", "waiting_for_user_input"}:
            return "waiting_user_input"
        if normalized in {"failed", "error", "interrupted", "cancelled"}:
            return "failed"
        return "completed"

    def _build_raw_event_compactor(self, *, thread_id: str | None, turn_id: str | None) -> _RawEventCompactorV3:
        return _RawEventCompactorV3(
            default_thread_id=thread_id,
            default_turn_id=turn_id,
            window_ms=self._coalescing_window_ms,
            max_batch_size=self._coalescing_max_batch_size,
        )

    @staticmethod
    def _extract_turn_status_from_raw_event(raw_event: dict[str, Any]) -> str | None:
        params = raw_event.get("params", {})
        turn_payload = params.get("turn", {}) if isinstance(params, dict) else {}
        raw_status = (
            str(turn_payload.get("status") or params.get("status") or "").strip().lower()
            if isinstance(turn_payload, dict)
            else str(params.get("status") or "").strip().lower()
        )
        return raw_status or None

    def _apply_raw_event_batch_v3(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        raw_events: list[dict[str, Any]],
        provisional_tool_calls: dict[str, dict[str, Any]],
        apply_turn_completed_event: bool,
        final_turn_status: str,
    ) -> str:
        if not raw_events:
            return final_turn_status

        current = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
            ensure_binding=False,
        )
        updated = current
        events: list[dict[str, Any]] = []
        resolved_turn_status = final_turn_status

        for raw_event in raw_events:
            method = str(raw_event.get("method") or "").strip()
            if not method:
                continue

            if method == "item/started":
                self._enrich_started_item_from_provisional_call(raw_event, provisional_tool_calls)

            if method == "turn/completed":
                maybe_status = self._extract_turn_status_from_raw_event(raw_event)
                if maybe_status:
                    resolved_turn_status = maybe_status
                if not apply_turn_completed_event:
                    continue

            updated, raw_batch_events = apply_raw_event_v3(updated, raw_event)
            events.extend(raw_batch_events)

        if events:
            self._persist_mutation_v3(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                snapshot=updated,
                events=events,
            )
        return resolved_turn_status

    @staticmethod
    def _looks_like_patch_text(text: str) -> bool:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        return (
            "*** Begin Patch" in normalized
            or "diff --git " in normalized
            or "\n@@ " in f"\n{normalized}"
            or "\n+++ " in f"\n{normalized}"
            or "\n--- " in f"\n{normalized}"
        )

    @classmethod
    def _tool_call_arguments_text(cls, arguments: Any) -> str | None:
        if isinstance(arguments, str):
            trimmed = arguments.strip()
            return trimmed or None

        if isinstance(arguments, dict):
            for key in ("input", "patch", "diff", "content", "text", "value", "body"):
                raw = arguments.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw
            for raw in arguments.values():
                if isinstance(raw, str) and cls._looks_like_patch_text(raw):
                    return raw
            if arguments:
                return json.dumps(arguments, ensure_ascii=True, sort_keys=True)

        return None

    @classmethod
    def _enrich_started_item_from_provisional_call(
        cls,
        raw_event: dict[str, Any],
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> None:
        params = raw_event.get("params", {})
        item = params.get("item", {}) if isinstance(params, dict) else {}
        if not isinstance(item, dict):
            return

        call_id = str(item.get("callId") or item.get("call_id") or "").strip()
        item_id = str(item.get("id") or "").strip()
        candidate_ids: list[str] = []
        if call_id:
            candidate_ids.append(call_id)
        if item_id and item_id not in candidate_ids:
            candidate_ids.append(item_id)

        matched_call_id: str | None = None
        record: dict[str, Any] | None = None
        for candidate_id in candidate_ids:
            candidate_record = provisional_tool_calls.get(candidate_id)
            if isinstance(candidate_record, dict):
                matched_call_id = candidate_id
                record = candidate_record
                break
        if record is None:
            return

        record["matched"] = True
        if not call_id and matched_call_id:
            item["callId"] = matched_call_id

        if not item.get("toolName") and record.get("toolName"):
            item["toolName"] = record.get("toolName")

        item_type = str(item.get("type") or "").strip()
        if item_type != "fileChange":
            return

        existing = item.get("argumentsText")
        if isinstance(existing, str) and existing.strip():
            return

        arguments_text = cls._tool_call_arguments_text(record.get("arguments"))
        if isinstance(arguments_text, str) and arguments_text.strip():
            item["argumentsText"] = arguments_text

    def build_error_item_for_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        turn_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> ConversationItemV3:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        resolved_thread_id = str(thread_id or snapshot.get("threadId") or "")
        return self._build_error_item(
            turn_id=turn_id,
            thread_id=resolved_thread_id,
            message=message,
            sequence=self._next_sequence(snapshot),
        )

    def _run_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        thread_id: str,
        turn_id: str,
        input_text: str,
    ) -> None:
        provisional_tool_calls: dict[str, dict[str, Any]] = {}
        final_turn_status = "completed"
        boundary_prompt_kind: str | None = None
        compactor = self._build_raw_event_compactor(thread_id=thread_id, turn_id=turn_id)

        def process_ready_raw_events(ready_raw_events: list[dict[str, Any]]) -> None:
            nonlocal final_turn_status
            final_turn_status = self._apply_raw_event_batch_v3(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                raw_events=ready_raw_events,
                provisional_tool_calls=provisional_tool_calls,
                apply_turn_completed_event=False,
                final_turn_status=final_turn_status,
            )

        def handle_raw_event(raw_event: dict[str, Any]) -> None:
            nonlocal final_turn_status
            method = str(raw_event.get("method") or "").strip()
            if not method:
                return
            if method == "item/tool/call":
                call_id = str(raw_event.get("call_id") or "").strip()
                if not call_id:
                    return
                params = raw_event.get("params", {})
                provisional_tool_calls[call_id] = {
                    "callId": call_id,
                    "toolName": str(params.get("tool_name") or params.get("toolName") or "").strip() or None
                    if isinstance(params, dict)
                    else None,
                    "arguments": params.get("arguments") if isinstance(params, dict) else {},
                    "threadId": str(raw_event.get("thread_id") or thread_id),
                    "turnId": str(raw_event.get("turn_id") or turn_id),
                    "createdAt": str(raw_event.get("received_at") or iso_now()),
                    "matched": False,
                }
                return
            ready_raw_events = compactor.push(raw_event)
            if ready_raw_events:
                process_ready_raw_events(ready_raw_events)

        try:
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            workspace_root = self._chat_service._workspace_root_from_snapshot(snapshot)
            prompt, boundary_prompt_kind = self._chat_service._build_prompt_for_turn(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                thread_role=thread_role,
                snapshot=snapshot,
                node=node,
                node_by_id=node_by_id,
                user_content=input_text,
            )
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only" if thread_role == "ask_planning" else None,
                on_raw_event=handle_raw_event,
            )
            process_ready_raw_events(compactor.flush())
            returned_status = str(result.get("turn_status") or "").strip().lower()
            if returned_status:
                final_turn_status = returned_status
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            policy_violation_message: str | None = None
            if thread_role == "ask_planning":
                policy_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                    ensure_binding=False,
                )
                if self._ask_turn_contains_file_change_items(policy_snapshot, turn_id):
                    policy_violation_message = _ASK_READ_ONLY_POLICY_ERROR
                    self._record_ask_guard_violation()
                    final_turn_status = "failed"
            outcome = self.outcome_from_turn_status(final_turn_status)
            error_item = None
            if outcome == "failed" and policy_violation_message:
                current_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                )
                error_item = self._build_error_item(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=policy_violation_message,
                    sequence=self._next_sequence(current_snapshot),
                )
            self.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                turn_id=turn_id,
                outcome=outcome,
                error_item=error_item,
            )
            waiting_for_user_input = final_turn_status in {
                "waiting_user_input",
                "waitingforuserinput",
                "waiting_for_user_input",
            }
            if not waiting_for_user_input:
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
                if boundary_prompt_kind == "local_review" and thread_role == "audit":
                    self._chat_service._mark_local_review_prompt_consumed(project_id, node_id)
                elif boundary_prompt_kind == "package_review" and thread_role == "audit":
                    self._chat_service._mark_package_review_prompt_consumed(project_id, node_id)
        except Exception as exc:
            logger.debug(
                "V3 thread turn failed for %s/%s/%s: %s",
                project_id,
                node_id,
                thread_role,
                exc,
                exc_info=True,
            )
            try:
                process_ready_raw_events(compactor.flush())
                self._flush_unmatched_provisional_tools(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    provisional_tool_calls=provisional_tool_calls,
                )
                current_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                )
                error_item = self._build_error_item(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=str(exc),
                    sequence=self._next_sequence(current_snapshot),
                )
                self.complete_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    turn_id=turn_id,
                    outcome="failed",
                    error_item=error_item,
                )
            finally:
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)

    @staticmethod
    def _ask_turn_contains_file_change_items(snapshot: ThreadSnapshotV3, turn_id: str) -> bool:
        for item in snapshot.get("items", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("turnId") or "") != str(turn_id):
                continue
            kind = str(item.get("kind") or "").strip()
            if kind == "diff":
                return True
            if kind == "tool":
                output_files = item.get("outputFiles")
                if isinstance(output_files, list) and len(output_files) > 0:
                    return True
        return False

    def _record_ask_guard_violation(self) -> None:
        metrics = self._ask_rollout_metrics_service
        if metrics is None:
            return
        try:
            metrics.record_guard_violation()
        except Exception:
            logger.debug("Failed to record ask guard violation metric.", exc_info=True)

    def _build_local_user_item(
        self,
        *,
        snapshot: ThreadSnapshotV3,
        thread_id: str,
        turn_id: str,
        text: str,
    ) -> ConversationItemV3:
        now = iso_now()
        return {
            "id": f"turn:{turn_id}:user",
            "kind": "message",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": self._next_sequence(snapshot),
            "createdAt": now,
            "updatedAt": now,
            "status": "completed",
            "source": "local",
            "tone": "neutral",
            "metadata": {},
            "role": "user",
            "text": text,
            "format": "markdown",
        }

    def _build_error_item(
        self,
        *,
        turn_id: str,
        thread_id: str,
        message: str,
        sequence: int,
    ) -> ConversationItemV3:
        now = iso_now()
        return {
            "id": f"error:{turn_id}",
            "kind": "error",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": sequence,
            "createdAt": now,
            "updatedAt": now,
            "status": "failed",
            "source": "backend",
            "tone": "danger",
            "metadata": {},
            "code": "conversation_turn_failed",
            "title": "Turn failed",
            "message": message,
            "recoverable": True,
            "relatedItemId": None,
        }

    def _flush_unmatched_provisional_tools(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRoleV3,
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> None:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, events = self._finalize_unmatched_provisional_tools(
            snapshot,
            provisional_tool_calls,
        )
        if events:
            self._persist_mutation_v3(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                snapshot=updated,
                events=events,
            )

    def _finalize_unmatched_provisional_tools(
        self,
        snapshot: ThreadSnapshotV3,
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
        updated = copy_snapshot_v3(snapshot)
        events: list[dict[str, Any]] = []
        for call_id, record in list(provisional_tool_calls.items()):
            if record.get("matched"):
                continue
            arguments = record.get("arguments") if isinstance(record.get("arguments"), dict) else {}
            arguments_text = json.dumps(arguments, ensure_ascii=True, sort_keys=True) if arguments else None
            item: ConversationItemV3 = {
                "id": f"tool-call:{call_id}",
                "kind": "tool",
                "threadId": str(record.get("threadId") or snapshot.get("threadId") or ""),
                "turnId": str(record.get("turnId") or snapshot.get("activeTurnId") or "") or None,
                "sequence": self._next_sequence(updated),
                "createdAt": str(record.get("createdAt") or iso_now()),
                "updatedAt": iso_now(),
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {"provisional": True},
                "toolType": "generic",
                "title": str(record.get("toolName") or "tool"),
                "toolName": record.get("toolName"),
                "callId": call_id,
                "argumentsText": arguments_text,
                "outputText": "",
                "outputFiles": [],
                "exitCode": None,
            }
            updated, upsert_events = upsert_item_v3(updated, item)
            events.extend(upsert_events)
            provisional_tool_calls[call_id]["matched"] = True
        return updated, events

    def _normalize_answers(self, answers: list[dict[str, Any]]) -> list[UserInputAnswerV3]:
        normalized_answers: list[UserInputAnswerV3] = []
        for answer in answers:
            normalized = normalize_user_input_answer_v3(answer)
            if normalized is not None:
                normalized_answers.append(normalized)
        if not normalized_answers:
            raise InvalidRequest("answers must contain at least one valid answer.")
        return normalized_answers

    def _find_pending_request(self, snapshot: ThreadSnapshotV3, request_id: str) -> dict[str, Any] | None:
        for pending in snapshot.get("uiSignals", {}).get("activeUserInputRequests", []):
            if str(pending.get("requestId") or "") == request_id:
                return pending
        return None

    @staticmethod
    def _next_sequence(snapshot: ThreadSnapshotV3) -> int:
        return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1
