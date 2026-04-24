from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.business.workflow_v2.errors import WorkflowV2Error
from backend.business.workflow_v2.models import ThreadRole
from backend.session_core_v2.errors import SessionCoreError

router = APIRouter(tags=["workflow-v4"])
logger = logging.getLogger(__name__)


class EnsureThreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    model: str | None = None
    modelProvider: str | None = None
    forceRebase: bool = False


def _service(request: Request) -> Any:
    return request.app.state.workflow_thread_binding_service_v2


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


def _unexpected_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": "ERR_INTERNAL",
            "message": "Unexpected internal error.",
            "details": {},
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
