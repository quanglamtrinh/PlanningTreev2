from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.session_core_v2.errors import SessionCoreError, error_envelope

router = APIRouter(tags=["session-v4"])
logger = logging.getLogger(__name__)
_SESSION_EVENT_PREFIXES: tuple[str, ...] = (
    "thread/",
    "turn/",
    "task/",
    "item/",
    "hook/",
    "rawResponseItem/",
    "serverRequest/",
)
_SESSION_EVENT_EXPLICIT_METHODS: frozenset[str] = frozenset({"error"})
_SESSION_TRACE_METHODS: frozenset[str] = frozenset(
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


def _is_allowed_session_event_method(method: str) -> bool:
    normalized = str(method or "").strip()
    if not normalized:
        return False
    if normalized in _SESSION_EVENT_EXPLICIT_METHODS:
        return True
    return normalized.startswith(_SESSION_EVENT_PREFIXES)


def _sse_event_name_for_method(method: str) -> str:
    normalized = str(method or "").strip()
    if normalized == "error":
        return "session/error"
    return normalized or "message"


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error_response(error: SessionCoreError) -> JSONResponse:
    details = error.details if isinstance(error.details, dict) else {}
    logger.warning(
        "session_v4 request failed",
        extra={
            "threadId": details.get("threadId"),
            "turnId": details.get("turnId"),
            "clientActionId": details.get("clientActionId"),
            "eventSeq": details.get("eventSeq"),
            "errorCode": error.code,
        },
    )
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


def _mcp(request: Request) -> Any:
    return request.app.state.mcp_integration_service


def _phase_not_enabled(endpoint: str, *, phase: str) -> JSONResponse:
    return _error_response(
        SessionCoreError(
            code="ERR_PHASE_NOT_ENABLED",
            message=f"{endpoint} is not enabled in Session Core V2 {phase}.",
            status_code=501,
            details={"phase": phase},
        )
    )


def _turns_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "session_core_v2_enable_turns", False))


def _events_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "session_core_v2_enable_events", False))


def _requests_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "session_core_v2_enable_requests", False))


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


class ThreadForkRequest(ThreadConfigOverrides):
    pass


class McpTurnContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    projectId: str
    nodeId: str
    role: str


class TurnStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: list[dict[str, Any]]
    model: str | None = None
    cwd: str | None = None
    approvalPolicy: str | dict[str, Any] | None = None
    approvalsReviewer: str | None = None
    sandboxPolicy: str | dict[str, Any] | None = None
    personality: str | None = None
    effort: str | None = None
    summary: str | dict[str, Any] | None = None
    serviceTier: str | None = None
    outputSchema: dict[str, Any] | None = None
    mcpContext: McpTurnContext | None = None


class TurnSteerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedTurnId: str = Field(min_length=1)
    input: list[dict[str, Any]]


class TurnInterruptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass


class InjectItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[dict[str, Any]] = Field(min_length=1)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolutionKey: str = Field(min_length=1)
    result: dict[str, Any]


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolutionKey: str = Field(min_length=1)
    reason: str | None = None


class McpRegistryServerRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class McpProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class McpContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mcpContext: McpTurnContext | None = None


class McpResourceReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1)
    uri: str = Field(min_length=1)


class McpToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    arguments: Any | None = None
    meta: Any | None = Field(default=None, alias="_meta")


class McpOauthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    scopes: list[str] | None = None
    timeoutSecs: int | None = None




@router.get("/v4/extensions/mcp/registry")
def mcp_registry_list_v4(request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_ok(_mcp(request).list_registry()))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_registry_list_v4 failed")
        return _unexpected_error_response()


@router.put("/v4/extensions/mcp/registry/servers/{serverId}")
def mcp_registry_upsert_v4(serverId: str, payload: McpRegistryServerRequest, request: Request) -> JSONResponse:
    try:
        data = payload.model_dump(by_alias=True, exclude_none=True)
        data["serverId"] = serverId
        return JSONResponse(status_code=200, content=_ok(_mcp(request).upsert_registry_server(data)))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_registry_upsert_v4 failed")
        return _unexpected_error_response()


@router.delete("/v4/extensions/mcp/registry/servers/{serverId}")
def mcp_registry_delete_v4(serverId: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_ok(_mcp(request).delete_registry_server(serverId)))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_registry_delete_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/extensions/mcp/registry/health")
def mcp_registry_health_v4(request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_ok(_mcp(request).registry_health()))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_registry_health_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/mcp-profile")
def mcp_profile_read_v4(projectId: str, nodeId: str, role: str, request: Request) -> JSONResponse:
    try:
        profile = _mcp(request).read_profile(projectId, nodeId, role)
        return JSONResponse(status_code=200, content=_ok({"profile": profile}))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_profile_read_v4 failed")
        return _unexpected_error_response()


@router.patch("/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/mcp-profile")
def mcp_profile_patch_v4(projectId: str, nodeId: str, role: str, payload: McpProfilePatchRequest, request: Request) -> JSONResponse:
    try:
        patch = payload.model_dump(by_alias=True, exclude_none=True)
        return JSONResponse(status_code=200, content=_ok(_mcp(request).write_profile(projectId, nodeId, role, patch)))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_profile_patch_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/mcp-profile/reset")
def mcp_profile_reset_v4(projectId: str, nodeId: str, role: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_ok(_mcp(request).reset_profile(projectId, nodeId, role)))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_profile_reset_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/mcp-effective-config")
def mcp_effective_config_v4(
    projectId: str,
    nodeId: str,
    role: str,
    request: Request,
    threadId: str | None = Query(default=None),
) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_ok(_mcp(request).preview_effective_config(projectId, nodeId, role, thread_id=threadId)))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("mcp_effective_config_v4 failed")
        return _unexpected_error_response()


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
        response = _manager(request).thread_start(payload.model_dump(exclude_none=True) if payload else {})
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
def session_thread_fork_v4(
    threadId: str,
    request: Request,
    payload: ThreadForkRequest | None = Body(default=None),
) -> JSONResponse:
    try:
        response = _manager(request).thread_fork(
            thread_id=threadId,
            payload=(payload.model_dump(exclude_none=True) if payload else {}),
        )
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_fork_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/{threadId}/turns")
def session_thread_turns_v4(
    threadId: str,
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
) -> JSONResponse:
    try:
        payload: dict[str, Any] = {}
        if cursor is not None:
            payload["cursor"] = cursor
        if limit is not None:
            payload["limit"] = limit
        response = _manager(request).thread_turns_list(thread_id=threadId, payload=payload)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_turns_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/loaded/list")
def session_thread_loaded_list_v4(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
) -> JSONResponse:
    try:
        payload: dict[str, Any] = {}
        if cursor is not None:
            payload["cursor"] = cursor
        if limit is not None:
            payload["limit"] = limit
        response = _manager(request).thread_loaded_list(payload=payload)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_loaded_list_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/unsubscribe")
def session_thread_unsubscribe_v4(threadId: str, request: Request) -> JSONResponse:
    try:
        response = _manager(request).thread_unsubscribe(thread_id=threadId)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_unsubscribe_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/models/list")
def session_models_list_v4(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    includeHidden: bool | None = Query(default=None),
) -> JSONResponse:
    try:
        payload: dict[str, Any] = {}
        if cursor is not None:
            payload["cursor"] = cursor
        if limit is not None:
            payload["limit"] = limit
        if includeHidden is not None:
            payload["includeHidden"] = includeHidden
        response = _manager(request).model_list(payload=payload)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_models_list_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/archive")
def session_thread_archive_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/archive", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/unarchive")
def session_thread_unarchive_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/unarchive", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/name/set")
def session_thread_name_set_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/name/set", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/metadata/update")
def session_thread_metadata_update_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/metadata/update", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/rollback")
def session_thread_rollback_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/rollback", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/compact/start")
def session_thread_compact_start_not_enabled(threadId: str) -> JSONResponse:
    del threadId
    return _phase_not_enabled("thread/compact/start", phase="Phase 2")


@router.post("/v4/session/threads/{threadId}/turns/start")
def session_turn_start_v4(threadId: str, payload: TurnStartRequest, request: Request) -> JSONResponse:
    if not _turns_enabled(request):
        return _phase_not_enabled("turn/start", phase="Phase 2")
    try:
        response = _manager(request).turn_start(thread_id=threadId, payload=payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_turn_start_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/turns/{turnId}/steer")
def session_turn_steer_v4(threadId: str, turnId: str, payload: TurnSteerRequest, request: Request) -> JSONResponse:
    if not _turns_enabled(request):
        return _phase_not_enabled("turn/steer", phase="Phase 2")
    try:
        response = _manager(request).turn_steer(
            thread_id=threadId,
            path_turn_id=turnId,
            payload=payload.model_dump(exclude_none=True),
        )
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_turn_steer_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/turns/{turnId}/interrupt")
def session_turn_interrupt_v4(
    threadId: str,
    turnId: str,
    payload: TurnInterruptRequest,
    request: Request,
) -> JSONResponse:
    if not _turns_enabled(request):
        return _phase_not_enabled("turn/interrupt", phase="Phase 2")
    try:
        _manager(request).turn_interrupt(
            thread_id=threadId,
            turn_id=turnId,
            payload=payload.model_dump(exclude_none=True),
        )
        return JSONResponse(status_code=200, content=_ok({}))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_turn_interrupt_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/inject-items")
def session_inject_items_v4(
    threadId: str,
    payload: InjectItemsRequest,
    request: Request,
) -> JSONResponse:
    if not _turns_enabled(request):
        return _phase_not_enabled("thread/inject_items", phase="Phase 2")
    try:
        response = _manager(request).thread_inject_items(
            thread_id=threadId,
            payload=payload.model_dump(exclude_none=True),
        )
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_inject_items_v4 failed")
        return _unexpected_error_response()




@router.post("/v4/session/threads/{threadId}/mcp/refresh")
def session_mcp_refresh_v4(threadId: str, payload: McpContextRequest, request: Request) -> JSONResponse:
    try:
        response = _manager(request).mcp_runtime_refresh(thread_id=threadId, payload=payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_mcp_refresh_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/{threadId}/mcp/status")
def session_mcp_status_v4(
    threadId: str,
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    detail: str | None = Query(default=None),
) -> JSONResponse:
    try:
        del threadId
        payload: dict[str, Any] = {}
        if cursor is not None:
            payload["cursor"] = cursor
        if limit is not None:
            payload["limit"] = limit
        if detail is not None:
            payload["detail"] = detail
        response = _manager(request).mcp_server_status_list(payload)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_mcp_status_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/mcp/resource/read")
def session_mcp_resource_read_v4(threadId: str, payload: McpResourceReadRequest, request: Request) -> JSONResponse:
    try:
        response = _manager(request).mcp_resource_read(thread_id=threadId, payload=payload.model_dump(by_alias=True, exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_mcp_resource_read_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/threads/{threadId}/mcp/tool/call")
def session_mcp_tool_call_v4(threadId: str, payload: McpToolCallRequest, request: Request) -> JSONResponse:
    try:
        response = _manager(request).mcp_server_tool_call(thread_id=threadId, payload=payload.model_dump(by_alias=True, exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_mcp_tool_call_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/mcp/oauth/login")
def session_mcp_oauth_login_v4(payload: McpOauthLoginRequest, request: Request) -> JSONResponse:
    try:
        response = _manager(request).mcp_server_oauth_login(payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_mcp_oauth_login_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/requests/pending")
def session_requests_pending_v4(request: Request) -> JSONResponse:
    if not _requests_enabled(request):
        return _phase_not_enabled("requests/pending", phase="Phase 3")
    try:
        response = _manager(request).requests_pending()
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_requests_pending_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/requests/{requestId}/resolve")
def session_requests_resolve_v4(requestId: str, payload: ResolveRequest, request: Request) -> JSONResponse:
    if not _requests_enabled(request):
        return _phase_not_enabled("requests/resolve", phase="Phase 3")
    try:
        _manager(request).request_resolve(request_id=requestId, payload=payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok({}))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_requests_resolve_v4 failed")
        return _unexpected_error_response()


@router.post("/v4/session/requests/{requestId}/reject")
def session_requests_reject_v4(requestId: str, payload: RejectRequest, request: Request) -> JSONResponse:
    if not _requests_enabled(request):
        return _phase_not_enabled("requests/reject", phase="Phase 3")
    try:
        _manager(request).request_reject(request_id=requestId, payload=payload.model_dump(exclude_none=True))
        return JSONResponse(status_code=200, content=_ok({}))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_requests_reject_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/{threadId}/events/journal-head")
def session_thread_events_journal_head_v4(threadId: str, request: Request) -> JSONResponse:
    """Latest journal sequence for a thread. Used to align the client replay cursor after hydrate (gap recovery)."""
    if not _events_enabled(request):
        return _phase_not_enabled("events/journal-head", phase="Phase 2")
    try:
        response = _manager(request).get_thread_journal_head(thread_id=threadId)
        return JSONResponse(status_code=200, content=_ok(response))
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_events_journal_head_v4 failed")
        return _unexpected_error_response()


@router.get("/v4/session/threads/{threadId}/events")
def session_thread_events_v4(
    threadId: str,
    request: Request,
    cursor: str | None = Query(default=None),
) -> Any:
    if not _events_enabled(request):
        return _phase_not_enabled("events/stream", phase="Phase 2")
    try:
        header_cursor = request.headers.get("Last-Event-ID")
        effective_cursor = header_cursor if header_cursor else cursor
        stream_state = _manager(request).open_event_stream(thread_id=threadId, cursor=effective_cursor)
        replay_events = stream_state["replayEvents"]
        subscriber_id = stream_state["subscriberId"]
        logger.info(
            "session_thread_events_v4 opened",
            extra={
                "threadId": threadId,
                "subscriberId": subscriber_id,
                "cursorEventId": effective_cursor,
                "replayEventCount": len(replay_events),
            },
        )

        def _encode_sse(event: dict[str, Any]) -> str:
            event_seq = event.get("eventSeq")
            method = str(event.get("method") or "")
            if not _is_allowed_session_event_method(method):
                raise SessionCoreError(
                    code="ERR_INTERNAL",
                    message=f"Session stream received unsupported event method: {method}",
                    status_code=500,
                    details={"threadId": threadId, "method": method, "eventSeq": event_seq},
                )
            data = json.dumps(event, ensure_ascii=True)
            event_name = _sse_event_name_for_method(method)
            return f"id: {event_seq}\nevent: {event_name}\ndata: {data}\n\n"

        def _iter_sse() -> Iterator[str]:
            try:
                for replay_event in replay_events:
                    method = str(replay_event.get("method") or "")
                    if not _is_allowed_session_event_method(method):
                        logger.warning(
                            "session_thread_events_v4 dropped non-session replay event",
                            extra={
                                "threadId": threadId,
                                "eventSeq": replay_event.get("eventSeq"),
                                "method": method,
                                "errorCode": "ERR_INTERNAL",
                            },
                        )
                        continue
                    if method in _SESSION_TRACE_METHODS:
                        logger.info(
                            "session_thread_events_v4 replay emit",
                            extra={
                                "threadId": threadId,
                                "subscriberId": subscriber_id,
                                "eventSeq": replay_event.get("eventSeq"),
                                "method": method,
                            },
                        )
                    yield _encode_sse(replay_event)
                while True:
                    item = _manager(request).read_stream_event(subscriber_id=subscriber_id, timeout_sec=15.0)
                    if item is None:
                        logger.info(
                            "session_thread_events_v4 stream ended: subscriber missing",
                            extra={"threadId": threadId, "subscriberId": subscriber_id},
                        )
                        break
                    if item == {}:
                        yield ": keep-alive\n\n"
                        continue
                    if item.get("__control") == "lagged":
                        logger.warning(
                            "session_thread_events_v4 stream ended: lagged",
                            extra={
                                "threadId": threadId,
                                "subscriberId": subscriber_id,
                                "skipped": item.get("skipped"),
                            },
                        )
                        break
                    method = str(item.get("method") or "")
                    if not _is_allowed_session_event_method(method):
                        logger.warning(
                            "session_thread_events_v4 dropped non-session live event",
                            extra={
                                "threadId": threadId,
                                "eventSeq": item.get("eventSeq"),
                                "method": method,
                                "errorCode": "ERR_INTERNAL",
                            },
                        )
                        continue
                    if method in _SESSION_TRACE_METHODS:
                        logger.info(
                            "session_thread_events_v4 live emit",
                            extra={
                                "threadId": threadId,
                                "subscriberId": subscriber_id,
                                "eventSeq": item.get("eventSeq"),
                                "method": method,
                            },
                        )
                    yield _encode_sse(item)
            finally:
                _manager(request).close_event_stream(subscriber_id=subscriber_id)
                logger.info(
                    "session_thread_events_v4 closed",
                    extra={"threadId": threadId, "subscriberId": subscriber_id},
                )

        return StreamingResponse(_iter_sse(), media_type="text/event-stream")
    except SessionCoreError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("session_thread_events_v4 failed")
        return _unexpected_error_response()
