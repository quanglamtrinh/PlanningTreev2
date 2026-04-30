from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap/status")
async def get_bootstrap_status(request: Request) -> dict:
    return request.app.state.project_service.bootstrap_status()
