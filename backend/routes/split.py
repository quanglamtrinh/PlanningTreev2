from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.errors.app_errors import SplitNotAllowed
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY, parse_route_split_mode_or_raise

router = APIRouter(tags=["split"])


class SplitNodeRequest(BaseModel):
    mode: str
    confirm_replace: bool = False


def _split_service(request: Request):
    return request.app.state.split_service


def _planning_event_broker(request: Request):
    return request.app.state.planning_event_broker


def _format_sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.post("/projects/{project_id}/nodes/{node_id}/split")
async def split_node(request: Request, project_id: str, node_id: str, body: SplitNodeRequest) -> JSONResponse:
    mode = parse_route_split_mode_or_raise(body.mode)
    if mode in CANONICAL_SPLIT_MODE_REGISTRY:
        raise SplitNotAllowed(
            f"Canonical split mode '{mode}' is not executable until the new split pipeline lands."
        )
    payload = _split_service(request).split_node(
        project_id,
        node_id,
        mode,
        body.confirm_replace,
    )
    return JSONResponse(status_code=202, content=payload)


@router.get("/projects/{project_id}/nodes/{node_id}/planning/history")
async def get_planning_history(request: Request, project_id: str, node_id: str) -> dict[str, Any]:
    return _split_service(request).get_planning_history(project_id, node_id)


@router.get("/projects/{project_id}/nodes/{node_id}/planning/events")
async def stream_planning_events(project_id: str, node_id: str, request: Request) -> StreamingResponse:
    _split_service(request).get_planning_history(project_id, node_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _planning_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
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
