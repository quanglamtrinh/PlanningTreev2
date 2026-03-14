from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.errors.app_errors import InvalidRequest

router = APIRouter(tags=["chat"])


class CreateMessageRequest(BaseModel):
    content: str


def _chat_service(request: Request):
    return request.app.state.chat_service


def _chat_event_broker(request: Request):
    return request.app.state.chat_event_broker


def _format_sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.get("/projects/{project_id}/nodes/{node_id}/chat/session")
async def get_session(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        return _chat_service(request).get_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/chat/messages")
async def create_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: CreateMessageRequest,
) -> dict[str, Any]:
    try:
        return _chat_service(request).create_message(project_id, node_id, body.content)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/chat/reset")
async def reset_session(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        return _chat_service(request).reset_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.get("/projects/{project_id}/nodes/{node_id}/chat/events")
async def stream_chat_events(project_id: str, node_id: str, request: Request) -> StreamingResponse:
    try:
        _chat_service(request).get_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _chat_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _chat_event_broker(request).unsubscribe(project_id, node_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
