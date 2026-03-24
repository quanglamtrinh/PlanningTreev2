from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nodes"])


class CreateChildRequest(BaseModel):
    parent_id: str


class UpdateNodeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class UpdateNodeDocumentRequest(BaseModel):
    content: str


class ClarifyAnswerUpdate(BaseModel):
    field_name: str = Field(..., min_length=1)
    selected_option_id: Optional[str] = None
    custom_answer: Optional[str] = None


class UpdateClarifyRequest(BaseModel):
    answers: list[ClarifyAnswerUpdate]


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
    if kind == "frame":
        with request.app.state.storage.project_lock(project_id):
            result = request.app.state.node_document_service.put_document(
                project_id, node_id, kind, body.content
            )
            request.app.state.node_detail_service.bump_frame_revision(project_id, node_id)
            return result

    return request.app.state.node_document_service.put_document(project_id, node_id, kind, body.content)


@router.get("/projects/{project_id}/nodes/{node_id}/detail-state")
async def get_detail_state(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.get_detail_state(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/finish-task")
async def finish_task(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.finish_task_service.finish_task(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-frame")
async def confirm_frame(request: Request, project_id: str, node_id: str) -> dict:
    detail_state = request.app.state.node_detail_service.confirm_frame(project_id, node_id)
    generation_error: str | None = None
    if detail_state["active_step"] == "spec":
        # Zero questions → auto-confirmed clarify → trigger AI spec generation
        if hasattr(request.app.state, "spec_generation_service"):
            try:
                request.app.state.spec_generation_service.generate_spec(project_id, node_id)
            except Exception as exc:
                logger.warning("Spec generation start failed: %s", exc)
                generation_error = str(exc)
    else:
        # Has questions → trigger AI clarify generation for richer options.
        # Non-fatal: deterministic seed already created by confirm_frame.
        try:
            request.app.state.clarify_generation_service.generate_clarify(project_id, node_id)
        except Exception:
            pass
    if generation_error:
        detail_state["generation_error"] = generation_error
    return detail_state


@router.get("/projects/{project_id}/nodes/{node_id}/clarify")
async def get_clarify(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.get_clarify(project_id, node_id)


@router.put("/projects/{project_id}/nodes/{node_id}/clarify")
async def update_clarify(
    request: Request, project_id: str, node_id: str, body: UpdateClarifyRequest
) -> dict:
    return request.app.state.node_detail_service.update_clarify_answers(
        project_id, node_id, [a.model_dump() for a in body.answers]
    )


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-clarify")
async def confirm_clarify(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.apply_clarify_to_frame(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-spec")
async def confirm_spec(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_detail_service.confirm_spec(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/generate-frame")
async def generate_frame(request: Request, project_id: str, node_id: str) -> JSONResponse:
    payload = request.app.state.frame_generation_service.generate_frame(project_id, node_id)
    return JSONResponse(status_code=202, content=payload)


@router.post("/projects/{project_id}/nodes/{node_id}/generate-clarify")
async def generate_clarify(request: Request, project_id: str, node_id: str) -> JSONResponse:
    payload = request.app.state.clarify_generation_service.generate_clarify(project_id, node_id)
    return JSONResponse(status_code=202, content=payload)


@router.get("/projects/{project_id}/nodes/{node_id}/clarify-generation-status")
async def get_clarify_generation_status(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.clarify_generation_service.get_generation_status(project_id, node_id)


@router.get("/projects/{project_id}/nodes/{node_id}/frame-generation-status")
async def get_frame_generation_status(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.frame_generation_service.get_generation_status(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/generate-spec")
async def generate_spec(request: Request, project_id: str, node_id: str) -> JSONResponse:
    payload = request.app.state.spec_generation_service.generate_spec(project_id, node_id)
    return JSONResponse(status_code=202, content=payload)


@router.get("/projects/{project_id}/nodes/{node_id}/spec-generation-status")
async def get_spec_generation_status(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.spec_generation_service.get_generation_status(project_id, node_id)


class AcceptLocalReviewRequest(BaseModel):
    summary: str = Field(..., min_length=1)


@router.post("/projects/{project_id}/nodes/{node_id}/accept-local-review")
async def accept_local_review(
    request: Request, project_id: str, node_id: str, body: AcceptLocalReviewRequest
) -> dict:
    return request.app.state.review_service.accept_local_review(project_id, node_id, body.summary)


@router.post("/projects/{project_id}/nodes/{node_id}/accept-rollup-review")
async def accept_rollup_review(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.review_service.accept_rollup_review(project_id, node_id)
