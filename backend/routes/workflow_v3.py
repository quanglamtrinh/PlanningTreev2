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
from backend.errors.app_errors import AppError, AskV3Disabled, InvalidRequest
from backend.storage.file_utils import new_id

router = APIRouter(tags=["workflow-v3"])

SSE_HEARTBEAT_INTERVAL_SEC = 15
_THREAD_MISMATCH_ERROR = "Thread id does not match any active route for this node."


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


class ResolveUserInputByIdRequest(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)


class StartTurnByIdRequest(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanActionByIdRequest(BaseModel):
    action: Literal["implement_plan", "send_changes"]
    planItemId: str
    revision: int
    text: str | None = None
    idempotencyKey: str | None = None


def _normalize_thread_id(value: Any) -> str:
    return str(value or "").strip()


def _is_ask_v3_backend_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state, "ask_v3_backend_enabled", True))


def _resolve_execution_audit_thread_role_by_state(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str | None:
    state = request.app.state.storage.workflow_state_store.read_state(project_id, node_id)
    if not isinstance(state, dict):
        return None
    if _normalize_thread_id(state.get("executionThreadId")) == thread_id:
        return "execution"
    if _normalize_thread_id(state.get("reviewThreadId")) == thread_id:
        return "audit"
    return None


def _resolve_ask_thread_role_from_registry(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str | None:
    registry_service = request.app.state.thread_registry_service_v2
    entry = registry_service.read_entry(project_id, node_id, "ask_planning")
    ask_thread_id = _normalize_thread_id(entry.get("threadId"))
    if not ask_thread_id:
        legacy_session = request.app.state.storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role="ask_planning",
        )
        seeded_entry, _ = registry_service.seed_from_legacy_session(
            project_id,
            node_id,
            "ask_planning",
            legacy_session,
        )
        ask_thread_id = _normalize_thread_id(seeded_entry.get("threadId"))
    if ask_thread_id == thread_id:
        if not _is_ask_v3_backend_enabled(request):
            raise AskV3Disabled()
        return "ask_planning"
    return None


def _resolve_thread_role_by_id_v3(
    request: Request,
    project_id: str,
    node_id: str,
    thread_id: str,
) -> str:
    request.app.state.chat_service._validate_node_exists(project_id, node_id)
    normalized_thread_id = _normalize_thread_id(thread_id)
    if not normalized_thread_id:
        raise InvalidRequest(_THREAD_MISMATCH_ERROR)

    execution_or_audit = _resolve_execution_audit_thread_role_by_state(
        request,
        project_id,
        node_id,
        normalized_thread_id,
    )
    if execution_or_audit is not None:
        return execution_or_audit

    ask_role = _resolve_ask_thread_role_from_registry(
        request,
        project_id,
        node_id,
        normalized_thread_id,
    )
    if ask_role is not None:
        return ask_role
    raise InvalidRequest(_THREAD_MISMATCH_ERROR)


@router.get("/projects/{project_id}/threads/by-id/{thread_id}")
async def get_thread_snapshot_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        snapshot_v2 = request.app.state.thread_query_service_v2.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
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
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
        if thread_role == "ask_planning":
            metrics = getattr(request.app.state, "ask_rollout_metrics_service", None)
            if metrics is not None:
                metrics.record_stream_session()
        snapshot_v2 = request.app.state.thread_query_service_v2.build_stream_snapshot(
            project_id,
            node_id,
            thread_role,
            after_snapshot_version=after_snapshot_version,
            ensure_binding=False,
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
        thread_role = _resolve_thread_role_by_id_v3(
            request,
            project_id,
            node_id,
            thread_id,
        )
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


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/turns")
async def start_turn_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    body: StartTurnByIdRequest,
    node_id: str = Query(...),
):
    try:
        workflow_service = request.app.state.execution_audit_workflow_service_v2
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role == "execution":
            idempotency_key = str(body.metadata.get("idempotencyKey") or new_id("exec_followup"))
            payload = workflow_service.start_execution_followup(
                project_id,
                node_id,
                idempotency_key=idempotency_key,
                text=body.text,
            )
        elif thread_role == "ask_planning":
            payload = request.app.state.thread_runtime_service_v2.start_turn(
                project_id,
                node_id,
                thread_role,
                body.text,
                metadata=body.metadata,
            )
        else:
            raise InvalidRequest("Audit review is read-only in the execution/audit thread flow.")
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
        workflow_service = request.app.state.execution_audit_workflow_service_v2
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role != "execution":
            raise InvalidRequest("Plan-ready actions are supported only on execution threads.")

        plan_item_id = str(body.planItemId or "").strip()
        if not plan_item_id:
            raise InvalidRequest("planItemId is required for plan-ready actions.")
        if int(body.revision) < 0:
            raise InvalidRequest("revision must be a non-negative integer.")

        snapshot_v2 = request.app.state.thread_query_service_v2.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=True,
            ensure_binding=False,
        )
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


@router.post("/projects/{project_id}/threads/by-id/{thread_id}/reset")
async def reset_thread_by_id_v3(
    request: Request,
    project_id: str,
    thread_id: str,
    node_id: str = Query(...),
):
    try:
        thread_role = _resolve_thread_role_by_id_v3(request, project_id, node_id, thread_id)
        if thread_role != "ask_planning":
            raise InvalidRequest("V3 by-id reset is supported only on ask threads.")
        snapshot = request.app.state.thread_query_service_v2.reset_thread(
            project_id,
            node_id,
            thread_role,
        )
        return _ok(
            {
                "threadId": snapshot.get("threadId"),
                "snapshotVersion": snapshot.get("snapshotVersion"),
            }
        )
    except AppError as exc:
        return _error_response(exc)
    except Exception:
        return _unexpected_error_response()
