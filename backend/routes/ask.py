from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.errors.app_errors import InvalidRequest

router = APIRouter(tags=["ask"])


class CreateAskMessageRequest(BaseModel):
    content: str


class CreatePacketRequest(BaseModel):
    summary: str
    context_text: str
    source_message_ids: list[str] | None = None


def _ask_service(request: Request):
    return request.app.state.ask_service


def _ask_event_broker(request: Request):
    return request.app.state.ask_event_broker


def _format_sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.get("/projects/{project_id}/nodes/{node_id}/ask/session")
async def get_session(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).get_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/messages")
async def create_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: CreateAskMessageRequest,
) -> dict[str, Any]:
    try:
        return _ask_service(request).create_message(project_id, node_id, body.content)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/reset")
async def reset_session(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).reset_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.get("/projects/{project_id}/nodes/{node_id}/ask/packets")
async def list_packets(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).list_packets(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/packets")
async def create_packet(
    request: Request,
    project_id: str,
    node_id: str,
    body: CreatePacketRequest,
) -> dict[str, Any]:
    try:
        return _ask_service(request).create_packet(
            project_id,
            node_id,
            body.summary,
            body.context_text,
            body.source_message_ids,
        )
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/approve")
async def approve_packet(request: Request, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).approve_packet(project_id, node_id, packet_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/reject")
async def reject_packet(request: Request, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).reject_packet(project_id, node_id, packet_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.post("/projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/merge")
async def merge_packet(request: Request, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
    try:
        return _ask_service(request).merge_packet(project_id, node_id, packet_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


@router.get("/projects/{project_id}/nodes/{node_id}/ask/events")
async def stream_ask_events(project_id: str, node_id: str, request: Request) -> StreamingResponse:
    try:
        _ask_service(request).get_session(project_id, node_id)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _ask_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
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
