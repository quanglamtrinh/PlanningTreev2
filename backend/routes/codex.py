from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["codex"])

SSE_HEARTBEAT_INTERVAL_SEC = 15


@router.get("/codex/account")
async def get_codex_account_snapshot(request: Request) -> dict:
    return request.app.state.codex_account_service.get_snapshot()


@router.get("/codex/usage/local")
async def get_local_usage_snapshot(
    request: Request,
    days: str | None = None,
) -> dict:
    service = request.app.state.local_usage_snapshot_service
    return await asyncio.to_thread(service.read_snapshot, days)


@router.get("/codex/events")
async def codex_events(request: Request) -> StreamingResponse:
    broker = request.app.state.codex_event_broker
    queue = broker.subscribe()

    async def event_generator():
        try:
            # Flush an initial comment so streaming clients can finish connecting
            # before the first snapshot update or periodic heartbeat arrives.
            yield ": connected\n\n"
            while True:
                try:
                    snapshot = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SEC)
                    data = json.dumps(snapshot, ensure_ascii=True)
                    yield f"event: snapshot_updated\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

                if await request.is_disconnected():
                    break
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
