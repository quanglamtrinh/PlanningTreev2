from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.business.workflow_v2.errors import WorkflowV2Error
from backend.errors.app_errors import AppError
from backend.session_core_v2.errors import SessionCoreError
from backend.split_contract import parse_route_split_mode_or_raise

router = APIRouter(tags=["artifacts-v4"])
logger = logging.getLogger(__name__)


class IdempotentArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)


class ClarifyAnswerUpdateV4(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    selected_option_id: str | None = None
    custom_answer: str | None = None


class ClarifyUpdateRequestV4(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[ClarifyAnswerUpdateV4]
    idempotencyKey: str | None = None


class SplitStartRequestV4(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1)
    mode: str = Field(min_length=1)


def _orchestrator(request: Request) -> Any:
    return request.app.state.artifact_orchestrator_v2


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


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/state")
def get_artifact_state_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_orchestrator(request).get_artifact_state(projectId, nodeId))
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_artifact_state_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/generate")
def generate_frame_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_frame_generation(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
        )
        return JSONResponse(status_code=202, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except Exception:
        logger.exception("generate_frame_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/generation-status")
def get_frame_generation_status_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).get_frame_generation_status(projectId, nodeId),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_frame_generation_status_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/confirm")
def confirm_frame_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).confirm_frame(
                projectId,
                nodeId,
                idempotency_key=payload.idempotencyKey,
            ),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("confirm_frame_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/generate")
def generate_clarify_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_clarify_generation(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
        )
        return JSONResponse(status_code=202, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except Exception:
        logger.exception("generate_clarify_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify")
def get_clarify_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_orchestrator(request).get_clarify(projectId, nodeId))
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_clarify_v4 failed")
        return _unexpected_error_response()


@router.put("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify")
def update_clarify_v4(
    projectId: str,
    nodeId: str,
    payload: ClarifyUpdateRequestV4,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).update_clarify(
            projectId,
            nodeId,
            answers=[answer.model_dump() for answer in payload.answers],
            idempotency_key=payload.idempotencyKey,
        )
        return JSONResponse(status_code=200, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("update_clarify_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/generation-status")
def get_clarify_generation_status_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).get_clarify_generation_status(projectId, nodeId),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_clarify_generation_status_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/confirm")
def confirm_clarify_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).confirm_clarify(
                projectId,
                nodeId,
                idempotency_key=payload.idempotencyKey,
            ),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("confirm_clarify_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/generate")
def generate_spec_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        response = _orchestrator(request).start_spec_generation(
            projectId,
            nodeId,
            idempotency_key=payload.idempotencyKey,
        )
        return JSONResponse(status_code=202, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except Exception:
        logger.exception("generate_spec_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/generation-status")
def get_spec_generation_status_v4(projectId: str, nodeId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).get_spec_generation_status(projectId, nodeId),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_spec_generation_status_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/confirm")
def confirm_spec_v4(
    projectId: str,
    nodeId: str,
    payload: IdempotentArtifactRequest,
    request: Request,
) -> JSONResponse:
    try:
        return JSONResponse(
            status_code=200,
            content=_orchestrator(request).confirm_spec(
                projectId,
                nodeId,
                idempotency_key=payload.idempotencyKey,
            ),
        )
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("confirm_spec_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/artifacts/split/start")
def start_split_v4(
    projectId: str,
    nodeId: str,
    payload: SplitStartRequestV4,
    request: Request,
) -> JSONResponse:
    try:
        mode = parse_route_split_mode_or_raise(payload.mode)
        response = _orchestrator(request).start_split(
            projectId,
            nodeId,
            mode=mode,
            idempotency_key=payload.idempotencyKey,
        )
        return JSONResponse(status_code=202, content=response)
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except SessionCoreError as exc:
        return _session_error_response(exc)
    except Exception:
        logger.exception("start_split_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/artifact-jobs/split/status")
def get_split_status_v4(projectId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_orchestrator(request).get_split_status(projectId))
    except WorkflowV2Error as exc:
        return _workflow_error_response(exc)
    except AppError as exc:
        return _app_error_response(exc)
    except Exception:
        logger.exception("get_split_status_v4 failed")
        return _unexpected_error_response()
