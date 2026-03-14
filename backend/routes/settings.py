from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["settings"])


class WorkspaceSettingsRequest(BaseModel):
    base_workspace_root: str


@router.get("/settings/workspace")
async def get_workspace_settings(request: Request) -> dict:
    return request.app.state.project_service.get_workspace_settings()


@router.patch("/settings/workspace")
async def patch_workspace_settings(request: Request, body: WorkspaceSettingsRequest) -> dict:
    return request.app.state.project_service.set_workspace_root(body.base_workspace_root)
