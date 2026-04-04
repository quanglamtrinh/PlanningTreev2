from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.errors.app_errors import InvalidRequest

router = APIRouter(tags=["chat"])


class SendMessageRequest(BaseModel):
    content: str


def _reject_legacy_ask_handlers(thread_role: str) -> None:
    if thread_role == "ask_planning":
        raise InvalidRequest("Ask lane is no longer served on /v1 chat APIs. Use /v3 by-id APIs.")


@router.get("/projects/{project_id}/nodes/{node_id}/chat/session")
async def get_chat_session(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str = Query("ask_planning"),
) -> dict:
    _reject_legacy_ask_handlers(thread_role)
    return request.app.state.chat_service.get_session(project_id, node_id, thread_role=thread_role)


@router.post("/projects/{project_id}/nodes/{node_id}/chat/message")
async def send_chat_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: SendMessageRequest,
    thread_role: str = Query("ask_planning"),
) -> dict:
    _reject_legacy_ask_handlers(thread_role)
    return request.app.state.chat_service.create_message(
        project_id,
        node_id,
        body.content,
        thread_role=thread_role,
    )


@router.post("/projects/{project_id}/nodes/{node_id}/chat/reset")
async def reset_chat_session(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str = Query("ask_planning"),
) -> dict:
    _reject_legacy_ask_handlers(thread_role)
    return request.app.state.chat_service.reset_session(project_id, node_id, thread_role=thread_role)


@router.get("/projects/{project_id}/nodes/{node_id}/chat/events")
async def chat_events(
    request: Request,
    project_id: str,
    node_id: str,
    thread_role: str = Query("ask_planning"),
) -> StreamingResponse:
    _reject_legacy_ask_handlers(thread_role)
    request.app.state.chat_service.get_session(project_id, node_id, thread_role=thread_role)
    broker = request.app.state.chat_event_broker
    queue = broker.subscribe(project_id, node_id, thread_role=thread_role)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    data = json.dumps(event, ensure_ascii=True)
                    yield f"event: message\ndata: {data}\n\n"
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
