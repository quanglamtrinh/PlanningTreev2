from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ThreadStatus = Literal["notLoaded", "idle", "running", "closed", "failed"]
RolloutVariant = Literal["session_meta", "turn_context", "event_msg", "response_item", "compacted"]


@dataclass(frozen=True)
class ThreadMetadata:
    thread_id: str
    project_id: str | None
    title: str | None
    created_at_ms: int
    updated_at_ms: int
    status: ThreadStatus
    rollout_path: str
    native_session_id: str | None = None
    forked_from_id: str | None = None
    archived_at_ms: int | None = None


@dataclass(frozen=True)
class RolloutLine:
    timestamp: str
    item: dict[str, Any]


def normalize_rollout_item(item: dict[str, Any]) -> dict[str, Any]:
    """Keep PlanningTree events in Codex-like rollout item variants."""

    variant = str(item.get("type") or "").strip()
    if variant in {"session_meta", "turn_context", "event_msg", "response_item", "compacted"}:
        return dict(item)
    if "method" in item or "params" in item:
        return {"type": "event_msg", "event": dict(item)}
    return {"type": "event_msg", "event": {"method": "unknown", "params": dict(item)}}
