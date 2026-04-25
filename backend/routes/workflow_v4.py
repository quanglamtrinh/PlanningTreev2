from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.business.workflow_v2.events import WorkflowEventV2
from backend.business.workflow_v2.errors import WorkflowV2Error
from backend.business.workflow_v2.models import ThreadRole, workflow_state_to_response
from backend.business.workflow_v2.state_machine import derive_allowed_actions
from backend.errors.app_errors import AppError
from backend.session_core_v2.errors import SessionCoreError

router = APIRouter(tags=["workflow-v4"])
logger = logging.getLogger(__name__)
SSE_HEARTBEAT_INTERVAL_SEC = 15

_V2_EVENT_TYPES = {
    "workflow/state_changed",
    "workflow/context_stale",
    "workflow/action_completed",
    "workflow/action_failed",
}


class EnsureThreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None
    forceRebase: bool = False


class ExecutionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None


class PackageReviewStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None


class WorkspaceGuardMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    expectedWorkspaceHash: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None


class ReviewGuardMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    expectedReviewCommitSha: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None


def _service(request: Request) -> Any:
    return request.app.state.workflow_thread_binding_service_v2


def _orchestrator(request: Request) -> Any:
    return request.app.state.execution_audit_orchestrator_v2


def _repository(request: Request) -> Any:
    return request.app.state.workflow_state_repository_v2


def _workflow_event_broker(request: Request) -> Any:
    return request.app.state.workflow_event_broker


def _workflow_error_response(error: WorkflowV2Error) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_envelope())


def _session_error_response(error: SessionCoreError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "details": error.details if isinstance(error.details, dict) else {},
        },
    )


def _app_error_response(error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "details": {},
        },
    )


def _unexpected_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": "ERR_INTERNAL",
            "message": "Unexpected internal error.",
            "details": {},
        },
    )


def _sse_frame(envelope: dict[str, Any]) -> str:
    event_id = str(envelope.get("eventId") or envelope.get("event_id") or "")
    data = json.dumps(envelope, ensure_ascii=True)
    if event_id:
        return f"id: {event_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


def _state_response(repository: Any, project_id: str, node_id: str) -> dict[str, Any]:
    state = repository.read_state(project_id, node_id)
    return workflow_state_to_response(
        state,
        allowed_actions=derive_allowed_actions(state),
    ).to_public_dict()


def _adapt_event_for_v4(repository: Any, event: dict[str, Any], project_id: str) -> dict[str, Any] | None:
    if str(event.get("projectId") or "") != project_id:
        return None

    event_type = str(event.get("type") or "")
    if event_type in _V2_EVENT_TYPES:
        return event

    if event_type != "node.workflow.updated":
        return None

    node_id = str(event.get("nodeId") or "")
    if not node_id:
        return None

    state = repository.read_state(project_id, node_id)
    event_payload: dict[str, Any] = {
        "type": "workflow/state_changed",
        "projectId": project_id,
        "nodeId": node_id,
        "phase": state.phase,
        "version": state.state_version,
        "details": {
            "legacyType": event_type,
            "legacyEventId": event.get("eventId"),
        },
    }
    event_id = str(event.get("eventId") or "").strip()
    if event_id:
        event_payload["eventId"] = event_id
    occurred_at = str(event.get("occurredAt") or "").strip()
    if occurred_at:
        event_payload["occurredAt"] = occurred_at
    return WorkflowEventV2(**event_payload).to_public_dict()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/workflow-state")
def get_workflow_state_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_state_response(_repository(request), projectId, nodeId))
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except Exception:
        logger.exception("get_workflow_state_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/events")
async def workflow_events_v4(request: Request, projectId: str) -> StreamingResponse:
    broker = _workflow_event_broker(request)
    repository = _repository(request)
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
                            "Closing Workflow V2 SSE stream for lagged subscriber (project=%s).",
                            projectId,
                        )
                        break
                    adapted = _adapt_event_for_v4(repository, event, projectId)
                    if adapted is not None:
                        yield _sse_frame(adapted)
                except asyncio.TimeoutError:
                    heartbeat_ticks += 1
                    if broker.consume_lagged_disconnect(queue):
                        logger.warning(
                            "Closing Workflow V2 SSE stream for lagged subscriber (project=%s).",
                            projectId,
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
        },
    )


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/ensure")
def ensure_workflow_thread_v4(
    projectId: str,
    nodeId: str,
    role: ThreadRole,
    payload: EnsureThreadRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _service(request).ensure_thread(
            project_id=projectId,
            node_id=nodeId,
            role=role,
            idempotency_key=payload.idempotencyKey,
            model=payload.model,
            model_provider=payload.modelProvider,
            force_rebase=payload.forceRebase,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except Exception:
        logger.exception("ensure_workflow_thread_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/execution/start")
def start_execution_v4(
    projectId: str,
    nodeId: str,
    payload: ExecutionStartRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_execution(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            model=payload.model,
            model_provider=payload.modelProvider,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("start_execution_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done")
def mark_done_from_execution_v4(
    projectId: str,
    nodeId: str,
    payload: WorkspaceGuardMutationRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).mark_done_from_execution(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            expected_workspace_hash=payload.expectedWorkspaceHash,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("mark_done_from_execution_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/execution/improve")
def improve_execution_v4(
    projectId: str,
    nodeId: str,
    payload: ReviewGuardMutationRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).request_improvements(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            expected_review_commit_sha=payload.expectedReviewCommitSha,
            model=payload.model,
            model_provider=payload.modelProvider,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("improve_execution_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/audit/start")
def start_audit_v4(
    projectId: str,
    nodeId: str,
    payload: WorkspaceGuardMutationRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_audit(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            expected_workspace_hash=payload.expectedWorkspaceHash,
            model=payload.model,
            model_provider=payload.modelProvider,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("start_audit_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/audit/accept")
def accept_audit_v4(
    projectId: str,
    nodeId: str,
    payload: ReviewGuardMutationRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).accept_audit(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            expected_review_commit_sha=payload.expectedReviewCommitSha,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("accept_audit_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/package-review/start")
def start_package_review_v4(
    projectId: str,
    nodeId: str,
    payload: PackageReviewStartRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_package_review(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
            model=payload.model,
            model_provider=payload.modelProvider,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("start_package_review_v4 failed")
        return _unexpected_error_response()
