from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["nodes"])


class CreateChildRequest(BaseModel):
    parent_id: str


class UpdateNodeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    purpose: Optional[str] = None
    responsibility: Optional[str] = None


class SpecMissionRequest(BaseModel):
    goal: Optional[str] = None
    success_outcome: Optional[str] = None
    implementation_level: Optional[str] = None


class SpecScopeRequest(BaseModel):
    must_do: Optional[list[str]] = None
    must_not_do: Optional[list[str]] = None
    deferred_work: Optional[list[str]] = None


class SpecConstraintsRequest(BaseModel):
    hard_constraints: Optional[list[str]] = None
    change_budget: Optional[str] = None
    touch_boundaries: Optional[list[str]] = None
    external_dependencies: Optional[list[str]] = None


class SpecAutonomyRequest(BaseModel):
    allowed_decisions: Optional[list[str]] = None
    requires_confirmation: Optional[list[str]] = None
    default_policy_when_unclear: Optional[str] = None


class SpecVerificationRequest(BaseModel):
    acceptance_checks: Optional[list[str]] = None
    definition_of_done: Optional[str] = None
    evidence_expected: Optional[list[str]] = None


class SpecExecutionControlsRequest(BaseModel):
    quality_profile: Optional[str] = None
    tooling_limits: Optional[list[str]] = None
    output_expectation: Optional[str] = None
    conflict_policy: Optional[str] = None
    missing_decision_policy: Optional[str] = None


class SpecAssumptionsRequest(BaseModel):
    assumptions_in_force: Optional[list[str]] = None


class UpdateSpecRequest(BaseModel):
    mission: Optional[SpecMissionRequest] = None
    scope: Optional[SpecScopeRequest] = None
    constraints: Optional[SpecConstraintsRequest] = None
    autonomy: Optional[SpecAutonomyRequest] = None
    verification: Optional[SpecVerificationRequest] = None
    execution_controls: Optional[SpecExecutionControlsRequest] = None
    assumptions: Optional[SpecAssumptionsRequest] = None


class PlanMessageRequest(BaseModel):
    content: str


class ToolRequestUserInputAnswerRequest(BaseModel):
    answers: list[str]


class ResolvePlanInputRequest(BaseModel):
    thread_id: Optional[str] = None
    turn_id: Optional[str] = None
    answers: dict[str, ToolRequestUserInputAnswerRequest]


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


@router.get("/projects/{project_id}/nodes/{node_id}/documents")
async def get_node_documents(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_service.get_documents(project_id, node_id)


@router.get("/projects/{project_id}/nodes/{node_id}/documents/task")
async def get_node_task(request: Request, project_id: str, node_id: str) -> dict:
    return {"task": request.app.state.node_service.get_task(project_id, node_id)}


@router.put("/projects/{project_id}/nodes/{node_id}/documents/task")
async def update_node_task(
    request: Request,
    project_id: str,
    node_id: str,
    body: UpdateTaskRequest,
) -> dict:
    updates = body.model_dump(exclude_none=True)
    return {"task": request.app.state.node_service.update_task(project_id, node_id, updates)}


@router.get("/projects/{project_id}/nodes/{node_id}/documents/brief")
async def get_node_brief(request: Request, project_id: str, node_id: str) -> dict:
    return {"brief": request.app.state.node_service.get_brief(project_id, node_id)}


@router.get("/projects/{project_id}/nodes/{node_id}/documents/briefing")
async def get_node_briefing(request: Request, project_id: str, node_id: str) -> dict:
    return {"briefing": request.app.state.node_service.get_briefing(project_id, node_id)}


@router.get("/projects/{project_id}/nodes/{node_id}/documents/spec")
async def get_node_spec(request: Request, project_id: str, node_id: str) -> dict:
    return {"spec": request.app.state.node_service.get_spec(project_id, node_id)}


@router.put("/projects/{project_id}/nodes/{node_id}/documents/spec")
async def update_node_spec(
    request: Request,
    project_id: str,
    node_id: str,
    body: UpdateSpecRequest,
) -> dict:
    updates = body.model_dump(exclude_none=True)
    return {"spec": request.app.state.node_service.update_spec(project_id, node_id, updates)}


@router.get("/projects/{project_id}/nodes/{node_id}/documents/state")
async def get_node_state(request: Request, project_id: str, node_id: str) -> dict:
    return {"state": request.app.state.node_service.get_state(project_id, node_id)}


@router.post("/projects/{project_id}/nodes/{node_id}/complete")
async def complete_node(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.node_service.complete_node(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-task")
async def confirm_task(request: Request, project_id: str, node_id: str) -> JSONResponse:
    state = request.app.state.node_service.confirm_task(project_id, node_id)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "operation": "brief_pipeline", "state": state},
    )


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-briefing")
async def confirm_briefing(request: Request, project_id: str, node_id: str) -> dict:
    return {"state": request.app.state.node_service.confirm_briefing(project_id, node_id)}


@router.post("/projects/{project_id}/nodes/{node_id}/confirm-spec")
async def confirm_spec(request: Request, project_id: str, node_id: str) -> dict:
    return {"state": request.app.state.node_service.confirm_spec(project_id, node_id)}


@router.post("/projects/{project_id}/nodes/{node_id}/generate-spec")
async def generate_spec(request: Request, project_id: str, node_id: str) -> JSONResponse:
    payload = request.app.state.spec_generation_service.start_generation(project_id, node_id)
    if isinstance(payload, dict) and payload.get("status") == "accepted":
        return JSONResponse(status_code=202, content=payload)
    return JSONResponse(status_code=200, content=payload)


@router.post("/projects/{project_id}/nodes/{node_id}/plan-and-execute")
async def plan_and_execute(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.chat_service.plan_and_execute(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/start-execution")
async def start_execution(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.chat_service.execute(project_id, node_id)


@router.post("/projects/{project_id}/nodes/{node_id}/plan/start")
async def start_plan(request: Request, project_id: str, node_id: str) -> JSONResponse:
    payload = request.app.state.chat_service.start_plan(project_id, node_id)
    return JSONResponse(status_code=202, content=payload)


@router.post("/projects/{project_id}/nodes/{node_id}/plan/messages")
async def send_plan_message(
    request: Request,
    project_id: str,
    node_id: str,
    body: PlanMessageRequest,
) -> JSONResponse:
    payload = request.app.state.chat_service.create_message(project_id, node_id, body.content)
    return JSONResponse(status_code=202, content=payload)


@router.post("/projects/{project_id}/nodes/{node_id}/plan/input/{request_id}/resolve")
async def resolve_plan_input(
    request: Request,
    project_id: str,
    node_id: str,
    request_id: str,
    body: ResolvePlanInputRequest,
) -> dict:
    return request.app.state.chat_service.resolve_plan_input(
        project_id,
        node_id,
        request_id,
        thread_id=body.thread_id,
        turn_id=body.turn_id,
        answers={
            question_id: {"answers": list(answer.answers)}
            for question_id, answer in body.answers.items()
        },
    )


@router.post("/projects/{project_id}/nodes/{node_id}/execute")
async def execute_node(request: Request, project_id: str, node_id: str) -> dict:
    return request.app.state.chat_service.execute(project_id, node_id)
