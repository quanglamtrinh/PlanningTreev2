from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["nodes"])


class CreateChildRequest(BaseModel):
    parent_id: str


class CreateTaskRequest(BaseModel):
    parent_id: str
    description: str = Field(..., min_length=1)


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


@router.post("/projects/{project_id}/nodes/create-task")
async def create_task_node(request: Request, project_id: str, body: CreateTaskRequest) -> dict:
    return request.app.state.node_service.create_task(
        project_id,
        body.parent_id,
        body.description,
    )


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


@router.get("/projects/{project_id}/nodes/{node_id}/review-state")
async def get_review_state(request: Request, project_id: str, node_id: str) -> dict:
    storage = request.app.state.storage
    tree_service = request.app.state.tree_service
    with storage.project_lock(project_id):
        snapshot = storage.project_store.load_snapshot(project_id)
        node_by_id = tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            from backend.errors.app_errors import NodeNotFound

            raise NodeNotFound(node_id)
        review_state = storage.workflow_domain_store.read_review(project_id, node_id)
        return review_state if isinstance(review_state, dict) else storage.workflow_domain_store.default_review()


@router.post("/projects/{project_id}/nodes/{node_id}/finish-task")
async def finish_task(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.execution_audit_orchestrator_v2.start_execution(
        project_id,
        node_id,
        idempotency_key=f"v4-finish-task:{uuid4().hex}",
    )


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-frame")
async def confirm_frame(request: Request, project_id: str, node_id: str) -> dict:
    detail_state = request.app.state.node_detail_service.confirm_frame(project_id, node_id)
    if detail_state["active_step"] == "clarify":
        # Non-fatal: deterministic seed already created by confirm_frame.
        try:
            request.app.state.clarify_generation_service.generate_clarify(project_id, node_id)
        except Exception:
            pass
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
    del body
    return request.app.state.execution_audit_orchestrator_v2.mark_done_from_execution(
        project_id,
        node_id,
        idempotency_key=f"v4-accept-local-review:{uuid4().hex}",
        expected_workspace_hash=request.app.state.workflow_state_repository_v2.read_state(project_id, node_id).workspace_hash or "",
    )


@router.post("/projects/{project_id}/nodes/{node_id}/accept-rollup-review")
async def accept_rollup_review(request: Request, project_id: str, node_id: str) -> dict:
    from backend.errors.app_errors import ReviewNotAllowed

    del request, project_id, node_id
    raise ReviewNotAllowed("Rollup review acceptance is available through Workflow V4 audit APIs.")


class ResetWorkspaceRequest(BaseModel):
    target: Literal["initial", "head"]


@router.post("/projects/{project_id}/nodes/{node_id}/reset-workspace")
async def reset_workspace(
    request: Request, project_id: str, node_id: str, body: ResetWorkspaceRequest
) -> dict:
    from backend.errors.app_errors import ResetWorkspaceNotAllowed

    storage = request.app.state.storage
    git_svc = request.app.state.git_checkpoint_service
    workflow_state = request.app.state.workflow_state_repository_v2.read_state(project_id, node_id)
    if workflow_state.phase in {"executing", "audit_running"}:
        raise ResetWorkspaceNotAllowed("Cannot reset workspace while a workflow turn is active.")

    target_sha = workflow_state.base_commit_sha if body.target == "initial" else workflow_state.head_commit_sha
    if not target_sha:
        raise ResetWorkspaceNotAllowed(f"No {body.target} SHA recorded for this node's workflow.")

    project_path = Path(storage.workspace_store.get_folder_path(project_id))
    git_svc.hard_reset(project_path, target_sha)
    detail_state = request.app.state.node_detail_service.get_detail_state(project_id, node_id)
    current_head = git_svc.get_head_sha(project_path)
    return {
        "status": "reset",
        "target_sha": target_sha,
        "current_head_sha": current_head,
        "task_present_in_current_workspace": current_head == workflow_state.head_commit_sha,
        "detail_state": detail_state,
    }
