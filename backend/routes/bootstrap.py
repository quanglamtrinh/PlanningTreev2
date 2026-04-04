from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap/status")
async def get_bootstrap_status(request: Request) -> dict:
    return request.app.state.project_service.bootstrap_status()


@router.get("/ask-rollout/metrics")
async def get_ask_rollout_metrics(request: Request) -> dict:
    metrics = getattr(request.app.state, "ask_rollout_metrics_service", None)
    if metrics is None:
        return {}
    return metrics.as_public_payload()


class AskRolloutMetricEventRequest(BaseModel):
    event: Literal["stream_reconnect", "stream_error"]


@router.post("/ask-rollout/metrics/events")
async def record_ask_rollout_metric_event(
    request: Request,
    body: AskRolloutMetricEventRequest,
) -> dict:
    metrics = getattr(request.app.state, "ask_rollout_metrics_service", None)
    if metrics is None:
        return {"ok": False}
    metrics.record_frontend_event(body.event)
    return {"ok": True}
