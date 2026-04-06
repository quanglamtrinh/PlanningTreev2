from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["projects"])


class AttachProjectRequest(BaseModel):
    folder_path: str


class ActiveNodeRequest(BaseModel):
    active_node_id: Optional[str] = None


class PutWorkspaceTextFileRequest(BaseModel):
    content: str = Field(default="")


@router.get("/projects")
async def list_projects(request: Request) -> list[dict]:
    return request.app.state.project_service.list_projects()


@router.post("/projects/attach")
async def attach_project(request: Request, body: AttachProjectRequest) -> dict:
    return request.app.state.project_service.attach_project_folder(body.folder_path)


@router.get("/projects/{project_id}/snapshot")
async def get_project_snapshot(request: Request, project_id: str) -> dict:
    return request.app.state.project_service.get_snapshot(project_id)


@router.post("/projects/{project_id}/reset-to-root")
async def reset_project_to_root(request: Request, project_id: str) -> dict:
    return request.app.state.project_service.reset_to_root(project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(request: Request, project_id: str) -> None:
    request.app.state.project_service.delete_project(project_id)


@router.patch("/projects/{project_id}/active-node")
async def set_active_node(request: Request, project_id: str, body: ActiveNodeRequest) -> dict:
    return request.app.state.node_service.set_active_node(project_id, body.active_node_id)


@router.post("/projects/{project_id}/git/init")
async def init_git(request: Request, project_id: str) -> dict:
    svc = request.app.state.git_checkpoint_service
    storage = request.app.state.storage
    project_path = Path(storage.workspace_store.get_folder_path(project_id))
    head_sha = svc.init_repo(project_path)
    return {"status": "initialized", "head_sha": head_sha, "message": "Git repository initialized."}


@router.get("/projects/{project_id}/workspace-text-file")
async def get_workspace_text_file(
    request: Request, project_id: str, relative_path: str
) -> dict:
    return request.app.state.workspace_file_service.get_text_file(project_id, relative_path)


@router.put("/projects/{project_id}/workspace-text-file")
async def put_workspace_text_file(
    request: Request,
    project_id: str,
    relative_path: str,
    body: PutWorkspaceTextFileRequest,
) -> dict:
    return request.app.state.workspace_file_service.put_text_file(
        project_id, relative_path, body.content
    )
