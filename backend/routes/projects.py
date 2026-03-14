from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    root_goal: str


class ActiveNodeRequest(BaseModel):
    active_node_id: Optional[str] = None


@router.get("/projects")
async def list_projects(request: Request) -> list[dict]:
    return request.app.state.project_service.list_projects()


@router.post("/projects")
async def create_project(request: Request, body: CreateProjectRequest) -> dict:
    return request.app.state.project_service.create_project(body.name, body.root_goal)


@router.get("/projects/{project_id}/snapshot")
async def get_project_snapshot(request: Request, project_id: str) -> dict:
    return request.app.state.project_service.get_snapshot(project_id)


@router.post("/projects/{project_id}/reset-to-root")
async def reset_project_to_root(request: Request, project_id: str) -> dict:
    return request.app.state.project_service.reset_to_root(project_id)


@router.patch("/projects/{project_id}/active-node")
async def set_active_node(request: Request, project_id: str, body: ActiveNodeRequest) -> dict:
    return request.app.state.node_service.set_active_node(project_id, body.active_node_id)
