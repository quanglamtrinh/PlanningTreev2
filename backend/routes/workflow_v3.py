from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.config.app_config import is_conversation_v3_bridge_allowed_for_project
from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_stream_open_envelope, build_thread_envelope
from backend.conversation.domain.types_v3 import normalize_thread_role_v3
from backend.errors.app_errors import AppError, AskV3Disabled, ConversationStreamMismatch, InvalidRequest
from backend.storage.file_utils import new_id

router = APIRouter(tags=["workflow-v3"])
logger = logging.getLogger(__name__)

SSE_HEARTBEAT_INTERVAL_SEC = 15
_THREAD_MISMATCH_ERROR = "Thread id does not match any active route for this node."
_THREAD_SNAPSHOT_LIVE_LIMIT_MAX = 5000
_THREAD_HISTORY_PAGE_LIMIT_DEFAULT = 200
_THREAD_HISTORY_PAGE_LIMIT_MAX = 1000


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": {},
            },
        },
    )


def _unexpected_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected internal error occurred.",
                "details": {},
            },
        },
    )


def _sse_frame(envelope: dict[str, object]) -> str:
    event_id = str(envelope.get("event_id") or envelope.get("eventId") or "")
    data = json.dumps(envelope, ensure_ascii=True)
    if event_id:
        return f"id: {event_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


class ResolveUserInputByIdRequest(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)


class StartTurnByIdRequest(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanActionByIdRequest(BaseModel):
    action: Literal["implement_plan", "send_changes"]
    planItemId: str
    revision: int
    text: str | None = None
    idempotencyKey: str | None = None


class WorkflowMutationRequest(BaseModel):
    idempotencyKey: str


class WorkspaceGuardMutationRequest(WorkflowMutationRequest):
    expectedWorkspaceHash: str


class ReviewGuardMutationRequest(WorkflowMutationRequest):
    expectedReviewCommitSha: str


def _workflow_service(request: Request) -> Any:
    return request.app.state.execution_audit_workflow_service


def _workflow_event_broker(request: Request) -> Any:
    return request.app.state.workflow_event_broker


def _normalize_thread_id(value: Any) -> str:
    return str(value or "").strip()


def _resolve_event_thread_id(envelope: dict[str, Any]) -> str:
    canonical_thread_id = _normalize_thread_id(envelope.get("thread_id"))
    if canonical_thread_id:
        return canonical_thread_id

    legacy_thread_id = _normalize_thread_id(envelope.get("threadId"))
    if legacy_thread_id:
        return legacy_thread_id

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return ""

    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot_thread_id = _normalize_thread_id(snapshot.get("threadId") or snapshot.get("thread_id"))
        if snapshot_thread_id:
            return snapshot_thread_id

    item = payload.get("item")
    if isinstance(item, dict):
        item_thread_id = _normalize_thread_id(item.get("threadId") or item.get("thread_id"))
        if item_thread_id:
            return item_thread_id

    return ""


_NUMERIC_CURSOR_PATTERN = re.compile(r"^\d+$")


def _normalize_numeric_cursor(value: Any, *, field_name: str) -> str | None:
    cursor = str(value or "").strip()
    if not cursor:
        return None
    if not _NUMERIC_CURSOR_PATTERN.match(cursor):
        raise InvalidRequest(f"{field_name} must be a numeric string.")
    return cursor


def _resolve_replay_cursor(request: Request, *, query_cursor: str | None) -> str | None:
    headers = getattr(request, "headers", {}) or {}
    header_get = headers.get if hasattr(headers, "get") else lambda *_args, **_kwargs: None
    header_cursor = _normalize_numeric_cursor(
        header_get("Last-Event-ID"),
        field_name="Last-Event-ID",
    )
    query_cursor_value = _normalize_numeric_cursor(query_cursor, field_name="last_event_id")
    return header_cursor if header_cursor is not None else query_cursor_value


def _resolve_event_id_int(envelope: dict[str, Any]) -> int | None:
    event_id = str(envelope.get("event_id") or envelope.get("eventId") or "").strip()
    if not event_id or not _NUMERIC_CURSOR_PATTERN.match(event_id):
        return None
    return int(event_id)


def _is_ask_v3_backend_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "ask_v3_backend_enabled", True))


def _snapshot_with_contract_fields(snapshot: dict[str, Any], *, thread_role: str) -> dict[str, Any]:
    prepared = copy.deepcopy(snapshot if isinstance(snapshot, dict) else {})
    resolved_thread_role = normalize_thread_role_v3(
        prepared.get("threadRole") or prepared.get("thread_role") or thread_role,
        default=normalize_thread_role_v3(thread_role, default="ask_planning"),
    )
    prepared["threadRole"] = resolved_thread_role
    prepared.pop("lane", None)
    return prepared


def _item_sequence_value(item: dict[str, Any]) -> int | None:
    raw = item.get("sequence")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def _sorted_snapshot_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = snapshot.get("items")
    if not isinstance(raw_items, list):
        return []
    items = [item for item in raw_items if isinstance(item, dict)]
    items.sort(key=lambda item: (_item_sequence_value(item) or 0, str(item.get("id") or "")))
    return items


def _build_history_meta(*, items: list[dict[str, Any]], total_item_count: int, has_older: bool) -> dict[str, Any]:
    oldest_visible_sequence = _item_sequence_value(items[0]) if items else None
    return {
        "hasOlder": bool(has_older),
        "oldestVisibleSequence": oldest_visible_sequence,
        "totalItemCount": max(0, int(total_item_count)),
    }


def _apply_live_item_limit(snapshot: dict[str, Any], *, live_limit: int | None) -> dict[str, Any]:
    prepared = copy.deepcopy(snapshot if isinstance(snapshot, dict) else {})
    items = _sorted_snapshot_items(prepared)
    total_item_count = len(items)
    if live_limit is None:
        prepared["items"] = items
        return prepared
    window = max(1, int(live_limit))
    has_older = total_item_count > window
    if has_older:
        items = items[-window:]
    prepared["items"] = items
    prepared["historyMeta"] = _build_history_meta(
        items=items,
        total_item_count=total_item_count,
        has_older=has_older,
    )
    return prepared


def _build_history_page(
    snapshot: dict[str, Any],
    *,
    before_sequence: int | None,
    limit: int,
) -> dict[str, Any]:
    items = _sorted_snapshot_items(snapshot)
    total_item_count = len(items)
    if before_sequence is not None:
        eligible = [
            item
            for item in items
            if (sequence := _item_sequence_value(item)) is not None and sequence < int(before_sequence)
        ]
    else:
        eligible = items
    window = max(1, int(limit))
    page_items = eligible[-window:]
    has_more = len(eligible) > len(page_items)
    next_before_sequence = _item_sequence_value(page_items[0]) if has_more and page_items else None
    return {
        "items": page_items,
        "has_more": has_more,
        "next_before_sequence": next_before_sequence,
        "total_item_count": total_item_count,
    }


def _envelope_with_contract_fields(envelope: dict[str, Any], *, thread_role: str) -> dict[str, Any]:
    prepared = copy.deepcopy(envelope if isinstance(envelope, dict) else {})
    prepared["threadRole"] = normalize_thread_role_v3(
        prepared.get("threadRole") or thread_role,
        default=normalize_thread_role_v3(thread_role, default="ask_planning"),
    )
    payload = prepared.get("payload")
    if isinstance(payload, dict):
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            payload["snapshot"] = _snapshot_with_contract_fields(snapshot, thread_role=thread_role)
    return prepared


def _resolve_execution_audit_thread_role_by_state(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str | None:
    state = request.app.state.storage.workflow_state_store.read_state(project_id, node_id)
    if not isinstance(state, dict):
        return None
    if _normalize_thread_id(state.get("executionThreadId")) == thread_id:
        return "execution"
    if _normalize_thread_id(state.get("reviewThreadId")) == thread_id:
        return "audit"
    return None


def _resolve_ask_thread_role_from_registry(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str | None:
    registry_service = request.app.state.thread_registry_service_v2
    entry = registry_service.read_entry(project_id, node_id, "ask_planning")
    ask_thread_id = _normalize_thread_id(entry.get("threadId"))
    if not ask_thread_id and is_conversation_v3_bridge_allowed_for_project(project_id):
        legacy_session = request.app.state.storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role="ask_planning",
        )
        seeded_entry, _ = registry_service.seed_from_legacy_session(
            project_id,
            node_id,
            "ask_planning",
            legacy_session,
        )
        ask_thread_id = _normalize_thread_id(seeded_entry.get("threadId"))
    if ask_thread_id == thread_id:
        if not _is_ask_v3_backend_enabled(request):
            raise AskV3Disabled()
        return "ask_planning"
    return None


def _resolve_thread_role_by_id_v3(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str:
    request.app.state.chat_service._validate_node_exists(project_id, node_id)
    normalized_thread_id = _normalize_thread_id(thread_id)
    if not normalized_thread_id:
        raise InvalidRequest(_THREAD_MISMATCH_ERROR)

    execution_or_audit = _resolve_execution_audit_thread_role_by_state(
        request,
        project_id,
        node_id,
        normalized_thread_id,
    )
    if execution_or_audit is not None:
        return execution_or_audit

    ask_role = _resolve_ask_thread_role_from_registry(
        request,
        project_id,
        node_id,
        normalized_thread_id,
    )
    if ask_role is not None:
        return ask_role
    raise InvalidRequest(_THREAD_MISMATCH_ERROR)


@router.get("/projects/{project_id}/nodes/{node_id}/workflow-state")
async def get_workflow_state_v3(request: Request, project_id: str, node_id: str):
    try:
        payload = _workflow_service(request).get_workflow_state(project_id, node_id)
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/finish-task")
async def finish_task_v3(
    request: Request,
    project_id: str,
    node_id: str,
    body: WorkflowMutationRequest,
):
    try:
        payload = _workflow_service(request).finish_task(
            project_id,
            node_id,
            idempotency_key=body.idempotencyKey,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution")
async def mark_done_from_execution_v3(
    request: Request,
    project_id: str,
    node_id: str,
    body: WorkspaceGuardMutationRequest,
):
    try:
        payload = _workflow_service(request).mark_done_from_execution(
            project_id,
            node_id,
            idempotency_key=body.idempotencyKey,
            expected_workspace_hash=body.expectedWorkspaceHash,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit")
async def review_in_audit_v3(
    request: Request,
    project_id: str,
    node_id: str,
    body: WorkspaceGuardMutationRequest,
):
    try:
        payload = _workflow_service(request).review_in_audit(
            project_id,
            node_id,
            idempotency_key=body.idempotencyKey,
            expected_workspace_hash=body.expectedWorkspaceHash,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit")
async def mark_done_from_audit_v3(
    request: Request,
    project_id: str,
    node_id: str,
    body: ReviewGuardMutationRequest,
):
    try:
        payload = _workflow_service(request).mark_done_from_audit(
            project_id,
            node_id,
            idempotency_key=body.idempotencyKey,
            expected_review_commit_sha=body.expectedReviewCommitSha,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution")
async def improve_in_execution_v3(
    request: Request,
    project_id: str,
    node_id: str,
    body: ReviewGuardMutationRequest,
):
    try:
        payload = _workflow_service(request).improve_in_execution(
            project_id,
            node_id,
            idempotency_key=body.idempotencyKey,
            expected_review_commit_sha=body.expectedReviewCommitSha,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/events")
async def workflow_events_v3(
    request: Request,
    project_id: str,
):
    broker = _workflow_event_broker(request)
    queue = broker.subscribe()

    async def event_generator():
        heartbeat_ticks = 0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    heartbeat_ticks = 0
                    if broker.consume_lagged_disconnect(queue):
                        logger.warning(
                            "Closing workflow SSE stream for lagged subscriber (project=%s).",
                            project_id,
                        )
                        break
                    if str(event.get("projectId") or "") != project_id:
                        continue
                    yield _sse_frame(event)
                except asyncio.TimeoutError:
                    heartbeat_ticks += 1
                    if broker.consume_lagged_disconnect(queue):
                        logger.warning(
                            "Closing workflow SSE stream for lagged subscriber (project=%s).",
                            project_id,
                        )
                        break
                    if heartbeat_ticks >= SSE_HEARTBEAT_INTERVAL_SEC:
                        heartbeat_ticks = 0
                        yield ": heartbeat\n\n"
                if await request.is_disconnected():
                    break
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/threads/by-id/{thread_id}")
async def get_thread_snapshot_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
    live_limit: int | None = Query(None, ge=1, le=_THREAD_SNAPSHOT_LIVE_LIMIT_MAX),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        snapshot_v3 = request.app.state.thread_query_service_v3.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
        )
        snapshot_v3 = _snapshot_with_contract_fields(snapshot_v3, thread_role=thread_role)
        snapshot_v3 = _apply_live_item_limit(snapshot_v3, live_limit=live_limit)
        return _ok({"snapshot": snapshot_v3})
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/threads/by-id/{thread_id}/history")
async def get_thread_history_page_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
    before_sequence: int | None = Query(None, ge=0),
    limit: int = Query(
        _THREAD_HISTORY_PAGE_LIMIT_DEFAULT,
        ge=1,
        le=_THREAD_HISTORY_PAGE_LIMIT_MAX,
    ),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        snapshot_v3 = request.app.state.thread_query_service_v3.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
        )
        snapshot_v3 = _snapshot_with_contract_fields(snapshot_v3, thread_role=thread_role)
        history_page = _build_history_page(
            snapshot_v3,
            before_sequence=before_sequence,
            limit=limit,
        )
        return _ok(history_page)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/threads/by-id/{thread_id}/events")
async def thread_events_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
    after_snapshot_version: int | None = None,
    last_event_id: str | None = None,
):
    broker = request.app.state.conversation_event_broker_v3
    queue = None
    thread_role = ""
    replay_cursor = None
    replay_frames: tuple[dict[str, Any], ...] = ()
    replay_tail_event_id: int | None = None
    try:
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        replay_cursor = _resolve_replay_cursor(request, query_cursor=last_event_id)
        if thread_role == "ask_planning":
            metrics = getattr(request.app.state, "ask_rollout_metrics_service", None)
            if metrics is not None:
                metrics.record_stream_session()
        snapshot_v3 = request.app.state.thread_query_service_v3.build_stream_snapshot(
            project_id,
            node_id,
            thread_role,
            after_snapshot_version=after_snapshot_version,
            ensure_binding=False,
        )
        queue = broker.subscribe(project_id, node_id, thread_role=thread_role)
    except AppError as exc:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _error_response(exc)
    except Exception:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _unexpected_error_response()

    resolved_thread_id = (
        _normalize_thread_id(thread_id)
        or _normalize_thread_id(snapshot_v3.get("threadId"))
        or f"unbound::{thread_role}"
    )
    first_snapshot_version = int(snapshot_v3.get("snapshotVersion") or 0)

    if replay_cursor is not None:
        replay_buffer = getattr(request.app.state, "thread_replay_buffer_service_v3", None)
        replay_result = (
            replay_buffer.read_business_events_since(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                thread_id=resolved_thread_id,
                last_event_id=replay_cursor,
            )
            if replay_buffer is not None
            else None
        )
        if replay_result is None or replay_result.replay_miss:
            if queue is not None:
                broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
            return _error_response(
                ConversationStreamMismatch(
                    "replay_miss: requested cursor is outside replay window; targeted resync required."
                )
            )
        replay_tail_event_id = replay_result.replay_tail_event_id
        replay_frames = tuple(
            _envelope_with_contract_fields(event, thread_role=thread_role) for event in replay_result.events
        )

    snapshot_envelope = None
    if replay_cursor is None:
        snapshot_event_id = request.app.state.thread_query_service_v3.issue_stream_event_id(
            project_id,
            node_id,
            thread_role,
            thread_id=resolved_thread_id,
        )
        snapshot_envelope = build_thread_envelope(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot_version=first_snapshot_version,
            event_type=event_types.THREAD_SNAPSHOT_V3,
            payload={"snapshot": _snapshot_with_contract_fields(snapshot_v3, thread_role=thread_role)},
            event_id=snapshot_event_id,
            thread_id=resolved_thread_id,
            turn_id=str(snapshot_v3.get("activeTurnId") or "").strip() or None,
        )
        snapshot_envelope = _envelope_with_contract_fields(snapshot_envelope, thread_role=thread_role)

    stream_open_envelope = build_stream_open_envelope(
        project_id=project_id,
        node_id=node_id,
        thread_role=thread_role,
        thread_id=resolved_thread_id,
        snapshot_version=first_snapshot_version,
        turn_id=str(snapshot_v3.get("activeTurnId") or "").strip() or None,
        payload={
            "streamStatus": "open",
            "threadId": resolved_thread_id,
            "threadRole": thread_role,
            "snapshotVersion": first_snapshot_version,
            "processingState": snapshot_v3.get("processingState"),
            "activeTurnId": snapshot_v3.get("activeTurnId"),
        },
    )

    async def event_generator():
        heartbeat_ticks = 0
        try:
            yield _sse_frame(stream_open_envelope)
            if snapshot_envelope is not None:
                yield _sse_frame(snapshot_envelope)
            elif replay_frames:
                for replay_frame in replay_frames:
                    yield _sse_frame(replay_frame)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    heartbeat_ticks = 0
                    if broker.consume_lagged_disconnect(project_id, node_id, queue, thread_role=thread_role):
                        logger.warning(
                            "Closing thread SSE stream for lagged subscriber (project=%s node=%s role=%s thread_id=%s).",
                            project_id,
                            node_id,
                            thread_role,
                            resolved_thread_id,
                        )
                        break
                    event_payload = event if isinstance(event, dict) else {}
                    if not event_payload:
                        continue
                    event_thread_id = _resolve_event_thread_id(event_payload)
                    if event_thread_id != resolved_thread_id:
                        logger.warning(
                            "Dropping thread event with mismatched thread_id: requested=%s event=%s project=%s node=%s role=%s event_type=%s event_id=%s",
                            resolved_thread_id,
                            event_thread_id or "<missing>",
                            project_id,
                            node_id,
                            thread_role,
                            str(event_payload.get("event_type") or event_payload.get("type") or ""),
                            str(event_payload.get("event_id") or event_payload.get("eventId") or ""),
                        )
                        continue
                    event_id = _resolve_event_id_int(event_payload)
                    if replay_tail_event_id is not None and event_id is not None and event_id <= replay_tail_event_id:
                        continue
                    event_version = int(event_payload.get("snapshotVersion") or 0)
                    if event_version and event_version <= first_snapshot_version:
                        continue
                    yield _sse_frame(_envelope_with_contract_fields(event_payload, thread_role=thread_role))
                except asyncio.TimeoutError:
                    heartbeat_ticks += 1
                    if broker.consume_lagged_disconnect(project_id, node_id, queue, thread_role=thread_role):
                        logger.warning(
                            "Closing thread SSE stream for lagged subscriber (project=%s node=%s role=%s thread_id=%s).",
                            project_id,
                            node_id,
                            thread_role,
                            resolved_thread_id,
                        )
                        break
                    if heartbeat_ticks >= SSE_HEARTBEAT_INTERVAL_SEC:
                        heartbeat_ticks = 0
                        yield ": heartbeat\n\n"
                if await request.is_disconnected():
                    break
        finally:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve")
async def resolve_user_input_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    request_id: str,
    body: ResolveUserInputByIdRequest,
    node_id: str = Query(...),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        payload = request.app.state.thread_runtime_service_v3.resolve_user_input(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            request_id=request_id,
            answers=body.answers,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/turns")
async def start_turn_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    body: StartTurnByIdRequest,
    node_id: str = Query(...),
):
    try:
        workflow_service = _workflow_service(request)
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role == "execution":
            idempotency_key = str(body.metadata.get("idempotencyKey") or new_id("exec_followup"))
            payload = workflow_service.start_execution_followup(
                project_id,
                node_id,
                idempotency_key=idempotency_key,
                text=body.text,
            )
        elif thread_role == "ask_planning":
            payload = request.app.state.thread_runtime_service_v3.start_turn(
                project_id,
                node_id,
                thread_role,
                body.text,
                metadata=body.metadata,
            )
        else:
            raise InvalidRequest("Audit review is read-only in the execution/audit thread flow.")
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/plan-actions")
async def apply_plan_action_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    body: PlanActionByIdRequest,
    node_id: str = Query(...),
):
    try:
        workflow_service = _workflow_service(request)
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role != "execution":
            raise InvalidRequest("Plan-ready actions are supported only on execution threads.")

        plan_item_id = str(body.planItemId or "").strip()
        if not plan_item_id:
            raise InvalidRequest("planItemId is required for plan-ready actions.")
        if int(body.revision) < 0:
            raise InvalidRequest("revision must be a non-negative integer.")

        snapshot_v3 = request.app.state.thread_query_service_v3.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
        )
        plan_ready = snapshot_v3.get("uiSignals", {}).get("planReady", {})
        if not bool(plan_ready.get("ready")) or bool(plan_ready.get("failed")):
            raise InvalidRequest("The current execution thread does not have a ready plan revision.")
        if str(plan_ready.get("planItemId") or "") != plan_item_id:
            raise InvalidRequest("planItemId does not match the active ready plan revision.")
        if int(plan_ready.get("revision") or -1) != int(body.revision):
            raise InvalidRequest("Plan revision is stale. Reload snapshot and retry.")

        text = str(body.text or "").strip()
        if not text:
            text = "Implement this plan." if body.action == "implement_plan" else "Send changes."
        idempotency_key = str(body.idempotencyKey or "").strip() or new_id("exec_followup")
        payload = workflow_service.start_execution_followup(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            text=text,
        )
        return _ok(
            {
                **payload,
                "action": body.action,
                "planItemId": plan_item_id,
                "revision": int(body.revision),
            }
        )
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/reset")
async def reset_thread_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role != "ask_planning":
            raise InvalidRequest("V3 by-id reset is supported only on ask threads.")
        snapshot = request.app.state.thread_query_service_v3.reset_thread(
            project_id,
            node_id,
            thread_role,
        )
        return _ok(
            {
                "threadId": snapshot.get("threadId"),
                "snapshotVersion": snapshot.get("snapshotVersion"),
            }
        )
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()
