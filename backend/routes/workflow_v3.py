from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.conversation.domain import events as event_types
from backend.conversation.domain.events import build_thread_envelope
from backend.conversation.projector.thread_event_projector_v3 import (
    project_v2_envelope_to_v3,
    project_v2_snapshot_to_v3,
)
from backend.errors.app_errors import AppError, InvalidRequest
from backend.storage.file_utils import new_id

router = APIRouter(tags=["workflow-v3"])

SSE_HEARTBEAT_INTERVAL_SEC = 15


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": {},
            },
        },
    )


def _unexpected_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected internal error occurred.",
                "details": {},
            },
        },
    )


def _sse_frame(envelope: dict[str, object]) -> str:
    event_id = str(envelope.get("eventId") or "")
    data = json.dumps(envelope, ensure_ascii=True)
    if event_id:
        return f"id: {event_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


def _require_v3_backend_enabled(request: Request) -> None:
    if getattr(request.app.state, "execution_audit_uiux_v3_backend_enabled", False):
        return
    raise InvalidRequest("execution_audit_uiux_v3_backend is disabled.")


class ResolveUserInputByIdRequest(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)


class PlanActionByIdRequest(BaseModel):
    action: Literal["implement_plan", "send_changes"]
    planItemId: str
    revision: int
    text: str | None = None
    idempotencyKey: str | None = None


@router.get("/projects/{project_id}/threads/by-id/{thread_id}")
async def get_thread_snapshot_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
):
    try:
        _require_v3_backend_enabled(request)
        snapshot_v2 = request.app.state.execution_audit_workflow_service_v2.get_thread_snapshot_by_id(
            project_id,
            node_id,
            thread_id,
        )
        snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)
        return _ok({"snapshot": snapshot_v3})
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.get("/projects/{project_id}/threads/by-id/{thread_id}/events")
async def thread_events_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
    after_snapshot_version: int | None = Query(None),
):
    broker = request.app.state.conversation_event_broker_v2
    queue = None
    thread_role = ""
    try:
        _require_v3_backend_enabled(request)
        thread_role, snapshot_v2 = request.app.state.execution_audit_workflow_service_v2.build_stream_snapshot_by_id(
            project_id,
            node_id,
            thread_id,
            after_snapshot_version=after_snapshot_version,
        )
        snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)
        queue = broker.subscribe(project_id, node_id, thread_role=thread_role)
    except AppError as exc:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _error_response(exc)
    except Exception:
        if queue is not None:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)
        return _unexpected_error_response()

    snapshot_envelope = build_thread_envelope(
        project_id=project_id,
        node_id=node_id,
        thread_role=thread_role,
        snapshot_version=int(snapshot_v3.get("snapshotVersion") or 0),
        event_type=event_types.THREAD_SNAPSHOT_V3,
        payload={"snapshot": snapshot_v3},
    )
    first_snapshot_version = int(snapshot_v3.get("snapshotVersion") or 0)

    async def event_generator():
        current_snapshot = snapshot_v3
        try:
            yield _sse_frame(snapshot_envelope)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SEC)
                    event_version = int(event.get("snapshotVersion") or 0)
                    if event_version and event_version <= first_snapshot_version:
                        continue
                    current_snapshot, mapped_events = project_v2_envelope_to_v3(current_snapshot, event)
                    if not mapped_events:
                        continue
                    for mapped in mapped_events:
                        mapped_payload = mapped.get("payload")
                        payload_dict = mapped_payload if isinstance(mapped_payload, dict) else {}
                        mapped_envelope = build_thread_envelope(
                            project_id=project_id,
                            node_id=node_id,
                            thread_role=thread_role,
                            snapshot_version=event_version or int(current_snapshot.get("snapshotVersion") or 0),
                            event_type=str(mapped.get("type") or ""),
                            payload=payload_dict,
                        )
                        yield _sse_frame(mapped_envelope)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                if await request.is_disconnected():
                    break
        finally:
            broker.unsubscribe(project_id, node_id, queue, thread_role=thread_role)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve")
async def resolve_user_input_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    request_id: str,
    body: ResolveUserInputByIdRequest,
    node_id: str = Query(...),
):
    try:
        _require_v3_backend_enabled(request)
        thread_role = request.app.state.execution_audit_workflow_service_v2.resolve_thread_route(
            project_id,
            node_id,
            thread_id,
        )
        if thread_role not in {"execution", "audit"}:
            raise InvalidRequest("V3 by-id user-input resolution supports only execution/audit threads.")
        payload = request.app.state.thread_runtime_service_v2.resolve_user_input(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            request_id=request_id,
            answers=body.answers,
        )
        return _ok(payload)
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/plan-actions")
async def apply_plan_action_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    body: PlanActionByIdRequest,
    node_id: str = Query(...),
):
    try:
        _require_v3_backend_enabled(request)
        workflow_service = request.app.state.execution_audit_workflow_service_v2
        thread_role = workflow_service.resolve_thread_route(project_id, node_id, thread_id)
        if thread_role != "execution":
            raise InvalidRequest("Plan-ready actions are supported only on execution threads.")

        plan_item_id = str(body.planItemId or "").strip()
        if not plan_item_id:
            raise InvalidRequest("planItemId is required for plan-ready actions.")
        if int(body.revision) < 0:
            raise InvalidRequest("revision must be a non-negative integer.")

        snapshot_v2 = workflow_service.get_thread_snapshot_by_id(project_id, node_id, thread_id)
        snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)
        plan_ready = snapshot_v3.get("uiSignals", {}).get("planReady", {})
        if not bool(plan_ready.get("ready")) or bool(plan_ready.get("failed")):
            raise InvalidRequest("The current execution thread does not have a ready plan revision.")
        if str(plan_ready.get("planItemId") or "") != plan_item_id:
            raise InvalidRequest("planItemId does not match the active ready plan revision.")
        if int(plan_ready.get("revision") or -1) != int(body.revision):
            raise InvalidRequest("Plan revision is stale. Reload snapshot and retry.")

        text = str(body.text or "").strip()
        if not text:
            text = "Implement this plan." if body.action == "implement_plan" else "Send changes."
        idempotency_key = str(body.idempotencyKey or "").strip() or new_id("exec_followup")
        payload = workflow_service.start_execution_followup(
            project_id,
            node_id,
            idempotency_key=idempotency_key,
            text=text,
        )
        return _ok(
            {
                **payload,
                "action": body.action,
                "planItemId": plan_item_id,
                "revision": int(body.revision),
            }
        )
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()
