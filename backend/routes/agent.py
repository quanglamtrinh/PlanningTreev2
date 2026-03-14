from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["agent"])


def _node_service(request: Request):
    return request.app.state.node_service


def _agent_event_broker(request: Request):
    return request.app.state.agent_event_broker


def _format_sse(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.get("/projects/{project_id}/nodes/{node_id}/agent/events")
async def stream_agent_events(project_id: str, node_id: str, request: Request) -> StreamingResponse:
    _node_service(request).get_state(project_id, node_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _agent_event_broker(request).subscribe(project_id, node_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _agent_event_broker(request).unsubscribe(project_id, node_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
