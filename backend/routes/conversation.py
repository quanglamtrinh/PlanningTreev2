from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.errors.app_errors import InvalidRequest

router = APIRouter(tags=["conversation"])


class ExecutionConversationSendRequest(BaseModel):
    content: str


class AskConversationSendRequest(BaseModel):
    content: str


class ExecutionConversationResolveRequestRequest(BaseModel):
    request_kind: str
    decision: str | None = None
    answers: dict[str, Any] | None = None
    thread_id: str | None = None
    turn_id: str | None = None


class ExecutionConversationCancelRequest(BaseModel):
    stream_id: str | None = None


def _conversation_gateway(request: Request):
    return request.app.state.conversation_gateway


def _conversation_event_broker(request: Request):
    return request.app.state.conversation_event_broker


def _ask_event_broker(request: Request):
    return request.app.state.ask_event_broker


def _planning_event_broker(request: Request):
    return request.app.state.planning_event_broker


def _format_sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/execution")
async def get_execution_conversation(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        conversation = _conversation_gateway(request).get_execution_conversation(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    return {"conversation": conversation}


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/send")
async def send_execution_conversation_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: ExecutionConversationSendRequest,
) -> JSONResponse:
    try:
        payload = _conversation_gateway(request).send_execution_message(project_id, node_id, body.content)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    return JSONResponse(status_code=202, content=payload)


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/requests/{request_id}/resolve")
async def resolve_execution_conversation_request(
    request: Request,
    project_id: str,
    node_id: str,
    request_id: str,
    body: ExecutionConversationResolveRequestRequest,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).resolve_execution_request(
            project_id,
            node_id,
            request_id,
            request_kind=body.request_kind,
            decision=body.decision,
            answers=body.answers,
            thread_id=body.thread_id,
            turn_id=body.turn_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/messages/{message_id}/continue")
async def continue_execution_conversation_message(
    request: Request,
    project_id: str,
    node_id: str,
    message_id: str,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).continue_execution_message(project_id, node_id, message_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/messages/{message_id}/retry")
async def retry_execution_conversation_message(
    request: Request,
    project_id: str,
    node_id: str,
    message_id: str,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).retry_execution_message(project_id, node_id, message_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/messages/{message_id}/regenerate")
async def regenerate_execution_conversation_message(
    request: Request,
    project_id: str,
    node_id: str,
    message_id: str,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).regenerate_execution_message(project_id, node_id, message_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/execution/cancel")
async def cancel_execution_conversation(
    request: Request,
    project_id: str,
    node_id: str,
    body: ExecutionConversationCancelRequest,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).cancel_execution_stream(
            project_id,
            node_id,
            stream_id=body.stream_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/ask")
async def get_ask_conversation(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        conversation = _conversation_gateway(request).get_ask_conversation(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    return {"conversation": conversation}


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/planning")
async def get_planning_conversation(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        conversation = _conversation_gateway(request).get_planning_conversation(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    return {"conversation": conversation}


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/planning/requests/{request_id}/resolve")
async def resolve_planning_conversation_request(
    request: Request,
    project_id: str,
    node_id: str,
    request_id: str,
    body: ExecutionConversationResolveRequestRequest,
) -> dict[str, Any]:
    try:
        return _conversation_gateway(request).resolve_planning_request(
            project_id,
            node_id,
            request_id,
            request_kind=body.request_kind,
            decision=body.decision,
            answers=body.answers,
            thread_id=body.thread_id,
            turn_id=body.turn_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/conversations/ask/send")
async def send_ask_conversation_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: AskConversationSendRequest,
) -> JSONResponse:
    try:
        payload = _conversation_gateway(request).send_ask_message(project_id, node_id, body.content)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    return JSONResponse(status_code=202, content=payload)


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/execution/events")
async def stream_execution_conversation_events(
    request: Request,
    project_id: str,
    node_id: str,
    after_event_seq: int = 0,
    expected_stream_id: str | None = None,
) -> StreamingResponse:
    try:
        conversation_id = _conversation_gateway(request).prepare_execution_event_stream(
            project_id,
            node_id,
            expected_stream_id=expected_stream_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _conversation_event_broker(request).subscribe(project_id, conversation_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    if int(event.get("event_seq", 0) or 0) <= after_event_seq:
                        continue
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _conversation_event_broker(request).unsubscribe(project_id, conversation_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/ask/events")
async def stream_ask_conversation_events(
    request: Request,
    project_id: str,
    node_id: str,
    after_event_seq: int = 0,
    expected_stream_id: str | None = None,
) -> StreamingResponse:
    try:
        conversation_id = _conversation_gateway(request).prepare_ask_event_stream(
            project_id,
            node_id,
            expected_stream_id=expected_stream_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _ask_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    legacy_event = await asyncio.wait_for(queue.get(), timeout=15)
                    translated_events = _conversation_gateway(request).translate_ask_event(legacy_event)
                    for event in translated_events:
                        if int(event.get("event_seq", 0) or 0) <= after_event_seq:
                            continue
                        if str(event.get("conversation_id") or "") != conversation_id:
                            continue
                        yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _ask_event_broker(request).unsubscribe(project_id, node_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/nodes/{node_id}/conversations/planning/events")
async def stream_planning_conversation_events(
    request: Request,
    project_id: str,
    node_id: str,
    after_event_seq: int = 0,
    expected_stream_id: str | None = None,
) -> StreamingResponse:
    try:
        conversation_id = _conversation_gateway(request).prepare_planning_event_stream(
            project_id,
            node_id,
            expected_stream_id=expected_stream_id,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _planning_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    legacy_event = await asyncio.wait_for(queue.get(), timeout=15)
                    translated_events = _conversation_gateway(request).translate_planning_event(
                        project_id,
                        node_id,
                        legacy_event
                    )
                    for event in translated_events:
                        if int(event.get("event_seq", 0) or 0) <= after_event_seq:
                            continue
                        if str(event.get("conversation_id") or "") != conversation_id:
                            continue
                        yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _planning_event_broker(request).unsubscribe(project_id, node_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
