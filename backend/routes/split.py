from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.split_contract import parse_route_split_mode_or_raise

router = APIRouter(tags=["split"])


class SplitNodeRequest(BaseModel):
    mode: str


@router.post("/projects/{project_id}/nodes/{node_id}/split")
async def split_node(request: Request, project_id: str, node_id: str, body: SplitNodeRequest) -> JSONResponse:
    mode = parse_route_split_mode_or_raise(body.mode)
    payload = request.app.state.split_service.split_node(project_id, node_id, mode)
    return JSONResponse(status_code=202, content=payload)


@router.get("/projects/{project_id}/split-status")
async def get_split_status(request: Request, project_id: str) -> dict:
    return request.app.state.split_service.get_split_status(project_id)
