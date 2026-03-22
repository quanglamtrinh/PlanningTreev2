from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["nodes"])


class CreateChildRequest(BaseModel):
    parent_id: str


class UpdateNodeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class UpdateNodeDocumentRequest(BaseModel):
    content: str


@router.post("/projects/{project_id}/nodes")
async def create_child_node(request: Request, project_id: str, body: CreateChildRequest) -> dict:
    return request.app.state.node_service.create_child(project_id, body.parent_id)


@router.patch("/projects/{project_id}/nodes/{node_id}")
async def update_node(request: Request, project_id: str, node_id: str, body: UpdateNodeRequest) -> dict:
    return request.app.state.node_service.update_node(
        project_id,
        node_id,
        title=body.title,
        description=body.description,
    )


@router.get("/projects/{project_id}/nodes/{node_id}/documents/{kind}")
async def get_node_document(request: Request, project_id: str, node_id: str, kind: str) -> dict:
    return request.app.state.node_document_service.get_document(project_id, node_id, kind)


@router.put("/projects/{project_id}/nodes/{node_id}/documents/{kind}")
async def update_node_document(
    request: Request,
    project_id: str,
    node_id: str,
    kind: str,
    body: UpdateNodeDocumentRequest,
) -> dict:
    result = request.app.state.node_document_service.put_document(project_id, node_id, kind, body.content)
    if kind == "frame":
        request.app.state.node_detail_service.bump_frame_revision(project_id, node_id)
    return result


@router.get("/projects/{project_id}/nodes/{node_id}/detail-state")
async def get_detail_state(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.get_detail_state(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-frame")
async def confirm_frame(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.confirm_frame(project_id, node_id)
