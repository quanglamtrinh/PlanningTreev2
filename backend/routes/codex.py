from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

router = APIRouter(tags=["usage"])


@router.get("/usage/local")
async def get_local_usage_snapshot(
    request: Request,
    days: str | None = None,
) -> dict:
    service = request.app.state.local_usage_snapshot_service
    return await asyncio.to_thread(service.read_snapshot, days)
