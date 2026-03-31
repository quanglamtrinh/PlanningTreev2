from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.errors.app_errors import AppError

router = APIRouter(tags=["workflow-v2"])

SSE_HEARTBEAT_INTERVAL_SEC = 15


class WorkflowMutationRequest(BaseModel):
    idempotencyKey: str


class WorkspaceGuardMutationRequest(WorkflowMutationRequest):
    expectedWorkspaceHash: str


class ReviewGuardMutationRequest(WorkflowMutationRequest):
    expectedReviewCommitSha: str


def _ok(data: dict) -> dict:
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
    event_id = str(envelope.get("eventId") or "")
    data = json.dumps(envelope, ensure_ascii=True)
    if event_id:
        return f"id: {event_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


@router.get("/projects/{project_id}/nodes/{node_id}/workflow-state")
async def get_workflow_state_v2(request: Request, project_id: str, node_id: str):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.get_workflow_state(project_id, node_id)
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/nodes/{node_id}/workflow/finish-task")
async def finish_task_v2(request: Request, project_id: str, node_id: str, body: WorkflowMutationRequest):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.finish_task(
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
async def mark_done_from_execution_v2(
    request: Request,
    project_id: str,
    node_id: str,
    body: WorkspaceGuardMutationRequest,
):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.mark_done_from_execution(
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
async def review_in_audit_v2(
    request: Request,
    project_id: str,
    node_id: str,
    body: WorkspaceGuardMutationRequest,
):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.review_in_audit(
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
async def mark_done_from_audit_v2(
    request: Request,
    project_id: str,
    node_id: str,
    body: ReviewGuardMutationRequest,
):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.mark_done_from_audit(
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
async def improve_in_execution_v2(
    request: Request,
    project_id: str,
    node_id: str,
    body: ReviewGuardMutationRequest,
):
    try:
        payload = request.app.state.execution_audit_workflow_service_v2.improve_in_execution(
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


@router.get("/projects/{project_id}/threads/by-id/{thread_id}")
async def get_thread_snapshot_by_id_v2(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
):
    try:
        snapshot = request.app.state.execution_audit_workflow_service_v2.get_thread_snapshot_by_id(
            project_id,
            node_id,
            thread_id,
        )
        return _ok({"snapshot": snapshot})
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/threads/by-id/{thread_id}/events")
async def thread_events_by_id_v2(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
    after_snapshot_version: int | None = Query(None),
):
    broker = request.app.state.conversation_event_broker_v2
    queue = None
    thread_role = ""
    try:
        thread_role, snapshot = request.app.state.execution_audit_workflow_service_v2.build_stream_snapshot_by_id(
            project_id,
            node_id,
            thread_id,
            after_snapshot_version=after_snapshot_version,
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
