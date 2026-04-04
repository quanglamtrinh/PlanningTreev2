from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.errors.app_errors import AppError, InvalidRequest

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
        raise InvalidRequest("Execution/audit thread by-id snapshot moved to /v3.")
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
    try:
        raise InvalidRequest("Execution/audit thread by-id events moved to /v3.")
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()
