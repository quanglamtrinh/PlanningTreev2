from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.errors.app_errors import AppError, InvalidRequest

router = APIRouter(tags=["conversation-v2"])

SSE_HEARTBEAT_INTERVAL_SEC = 15


class StartTurnRequest(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolveUserInputRequest(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)


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


def _sse_frame(envelope: dict[str, Any]) -> str:
    event_id = str(envelope.get("eventId") or "")
    data = json.dumps(envelope, ensure_ascii=True)
    if event_id:
        return f"id: {event_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


def _reject_legacy_thread_role_v2(thread_role: str) -> None:
    if thread_role in {"ask_planning", "execution", "audit"}:
        raise InvalidRequest("Thread role is no longer served on /v2. Use /v3 by-id APIs.")


@router.get("/projects/{project_id}/nodes/{node_id}/threads/{thread_role}")
async def get_thread_snapshot_v2(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str,
):
    try:
        _reject_legacy_thread_role_v2(thread_role)
        snapshot = request.app.state.thread_query_service_v2.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
        )
        return _ok({"snapshot": snapshot})
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/events")
async def thread_events_v2(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str,
    after_snapshot_version: int | None = Query(None),
):
    broker = request.app.state.conversation_event_broker_v2
    queue = None
    try:
        _reject_legacy_thread_role_v2(thread_role)
        queue = broker.subscribe(project_id, node_id, thread_role=thread_role)
        snapshot = request.app.state.thread_query_service_v2.build_stream_snapshot(
            project_id,
            node_id,
            thread_role,
            after_snapshot_version=after_snapshot_version,
        )
    except AppError as exc:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _error_response(exc)
    except Exception:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _unexpected_error_response()

    snapshot_envelope = build_thread_envelope(
        project_id=project_id,
        node_id=node_id,
        thread_role=thread_role,
        snapshot_version=int(snapshot.get("snapshotVersion") or 0),
        event_type=event_types.THREAD_SNAPSHOT,
        payload={"snapshot": snapshot},
    )
    first_snapshot_version = int(snapshot.get("snapshotVersion") or 0)

    async def event_generator():
        try:
            yield _sse_frame(snapshot_envelope)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SEC)
                    event_version = int(event.get("snapshotVersion") or 0)
                    if event_version and event_version <= first_snapshot_version:
                        continue
                    yield _sse_frame(event)
                except asyncio.TimeoutError:
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


@router.post("/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/turns")
async def start_turn_v2(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str,
    body: StartTurnRequest,
):
    try:
        _reject_legacy_thread_role_v2(thread_role)
        payload = request.app.state.thread_runtime_service_v2.start_turn(
            project_id,
            node_id,
            thread_role,
            body.text,
            metadata=body.metadata,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/requests/{request_id}/resolve")
async def resolve_user_input_v2(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str,
    request_id: str,
    body: ResolveUserInputRequest,
):
    try:
        _reject_legacy_thread_role_v2(thread_role)
        payload = request.app.state.thread_runtime_service_v2.resolve_user_input(
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


@router.post("/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/reset")
async def reset_thread_v2(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str,
):
    try:
        _reject_legacy_thread_role_v2(thread_role)
        snapshot = request.app.state.thread_query_service_v2.reset_thread(
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


@router.get("/projects/{project_id}/events")
async def workflow_events_v2(
    request: Request,
    project_id: str,
):
    broker = request.app.state.workflow_event_broker
    queue = broker.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SEC)
                    if str(event.get("projectId") or "") != project_id:
                        continue
                    yield _sse_frame(event)
                except asyncio.TimeoutError:
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
