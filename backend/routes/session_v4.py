from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.session_core_v2.errors import SessionCoreError, error_envelope

router = APIRouter(tags=["session-v4"])
logger = logging.getLogger(__name__)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error_response(error: SessionCoreError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error_envelope(error))


def _unexpected_error_response() -> JSONResponse:
    error = SessionCoreError(
        code="ERR_INTERNAL",
        message="Unexpected internal error.",
        status_code=500,
        details={},
    )
    return JSONResponse(status_code=500, content=error_envelope(error))


def _manager(request: Request) -> Any:
    return request.app.state.session_manager_v2


def _phase_not_enabled(endpoint: str) -> JSONResponse:
    return _error_response(
        SessionCoreError(
            code="ERR_PHASE_NOT_ENABLED",
            message=f"{endpoint} is not enabled in Session Core V2 Phase 1.",
            status_code=501,
            details={"phase": "P1"},
        )
    )


def _parse_csv_or_repeated_query(request: Request, key: str) -> list[str] | None:
    raw_values = list(request.query_params.getlist(key))
    if not raw_values:
        return None
    values: list[str] = []
    for raw in raw_values:
        if "," in raw:
            values.extend(part.strip() for part in raw.split(","))
        else:
            values.append(raw.strip())
    cleaned = [value for value in values if value]
    return cleaned or None


class InitializeCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experimentalApi: bool | None = False
    optOutNotificationMethods: list[str] | None = None


class ClientInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    title: str | None = None
    version: str


class InitializeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clientInfo: ClientInfo
    capabilities: InitializeCapabilities | None = None


class ThreadConfigOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = None
    modelProvider: str | None = None
    cwd: str | None = None
    approvalPolicy: str | dict[str, Any] | None = None
    approvalsReviewer: str | None = None
    personality: str | None = None
    sandbox: str | dict[str, Any] | None = None
    serviceTier: str | None = None
    baseInstructions: str | None = None
    developerInstructions: str | None = None
    config: dict[str, Any] | None = None
    ephemeral: bool | None = None


class ThreadStartRequest(ThreadConfigOverrides):
    pass


class ThreadResumeRequest(ThreadConfigOverrides):
    pass


@router.post("/v4/session/initialize")
def session_initialize_v4(payload: InitializeRequest, request: Request) -> JSONResponse:
    try:
        response = _manager(request).initialize(payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_initialize_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/status")
def session_status_v4(request: Request) -> JSONResponse:
    try:
        response = _manager(request).status()
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_status_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/start")
def session_thread_start_v4(
    request: Request,
    payload: ThreadStartRequest | None = Body(default=None),
) -> JSONResponse:
    try:
        response = _manager(request).thread_start((payload.model_dump(exclude_none=True) if payload else {}))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_start_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/resume")
def session_thread_resume_v4(
    threadId: str,
    request: Request,
    payload: ThreadResumeRequest | None = Body(default=None),
) -> JSONResponse:
    try:
        response = _manager(request).thread_resume(
            thread_id=threadId,
            payload=(payload.model_dump(exclude_none=True) if payload else {}),
        )
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_resume_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/list")
def session_thread_list_v4(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    archived: bool | None = Query(default=None),
    cwd: str | None = Query(default=None),
    sortKey: str | None = Query(default=None),
    searchTerm: str | None = Query(default=None),
) -> JSONResponse:
    try:
        payload: dict[str, Any] = {}
        if cursor is not None:
            payload["cursor"] = cursor
        if limit is not None:
            payload["limit"] = limit
        if archived is not None:
            payload["archived"] = archived
        if cwd is not None:
            payload["cwd"] = cwd
        if sortKey is not None:
            payload["sortKey"] = sortKey
        if searchTerm is not None:
            payload["searchTerm"] = searchTerm
        model_providers = _parse_csv_or_repeated_query(request, "modelProviders")
        if model_providers is not None:
            payload["modelProviders"] = model_providers
        source_kinds = _parse_csv_or_repeated_query(request, "sourceKinds")
        if source_kinds is not None:
            payload["sourceKinds"] = source_kinds
        response = _manager(request).thread_list(payload)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_list_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/{threadId}/read")
def session_thread_read_v4(
    threadId: str,
    request: Request,
    includeTurns: bool = Query(default=False),
) -> JSONResponse:
    try:
        response = _manager(request).thread_read(thread_id=threadId, include_turns=includeTurns)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_read_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/fork")
def session_thread_fork_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/fork")


@router.get("/v4/session/threads/{threadId}/turns")
def session_thread_turns_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/turns/list")


@router.get("/v4/session/threads/loaded/list")
def session_thread_loaded_list_not_enabled() -> JSONResponse:
    return _phase_not_enabled("thread/loaded/list")


@router.post("/v4/session/threads/{threadId}/unsubscribe")
def session_thread_unsubscribe_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/unsubscribe")


@router.post("/v4/session/threads/{threadId}/archive")
def session_thread_archive_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/archive")


@router.post("/v4/session/threads/{threadId}/unarchive")
def session_thread_unarchive_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/unarchive")


@router.post("/v4/session/threads/{threadId}/name/set")
def session_thread_name_set_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/name/set")


@router.post("/v4/session/threads/{threadId}/metadata/update")
def session_thread_metadata_update_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/metadata/update")


@router.post("/v4/session/threads/{threadId}/rollback")
def session_thread_rollback_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/rollback")


@router.post("/v4/session/threads/{threadId}/compact/start")
def session_thread_compact_start_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/compact/start")


@router.post("/v4/session/threads/{threadId}/turns/start")
def session_turn_start_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("turn/start")


@router.post("/v4/session/threads/{threadId}/turns/{turnId}/steer")
def session_turn_steer_not_enabled(threadId: str, turnId: str) -> JSONResponse:
    del threadId, turnId
    return _phase_not_enabled("turn/steer")


@router.post("/v4/session/threads/{threadId}/turns/{turnId}/interrupt")
def session_turn_interrupt_not_enabled(threadId: str, turnId: str) -> JSONResponse:
    del threadId, turnId
    return _phase_not_enabled("turn/interrupt")


@router.post("/v4/session/threads/{threadId}/inject-items")
def session_inject_items_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/inject_items")


@router.get("/v4/session/requests/pending")
def session_requests_pending_not_enabled() -> JSONResponse:
    return _phase_not_enabled("requests/pending")


@router.post("/v4/session/requests/{requestId}/resolve")
def session_requests_resolve_not_enabled(requestId: str) -> JSONResponse:
    del requestId
    return _phase_not_enabled("requests/resolve")


@router.post("/v4/session/requests/{requestId}/reject")
def session_requests_reject_not_enabled(requestId: str) -> JSONResponse:
    del requestId
    return _phase_not_enabled("requests/reject")


@router.get("/v4/session/threads/{threadId}/events")
def session_thread_events_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("events/stream")

