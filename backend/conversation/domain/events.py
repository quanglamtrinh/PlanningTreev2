from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.storage.file_utils import iso_now, new_id

THREAD_CHANNEL = "thread"
WORKFLOW_CHANNEL = "workflow"

THREAD_SNAPSHOT = "thread.snapshot"
CONVERSATION_ITEM_UPSERT = "conversation.item.upsert"
CONVERSATION_ITEM_PATCH = "conversation.item.patch"
THREAD_LIFECYCLE = "thread.lifecycle"
CONVERSATION_REQUEST_USER_INPUT_REQUESTED = "conversation.request.user_input.requested"
CONVERSATION_REQUEST_USER_INPUT_RESOLVED = "conversation.request.user_input.resolved"
THREAD_RESET = "thread.reset"
THREAD_ERROR = "thread.error"

THREAD_SNAPSHOT_V3 = "thread.snapshot.v3"
CONVERSATION_ITEM_UPSERT_V3 = "conversation.item.upsert.v3"
CONVERSATION_ITEM_PATCH_V3 = "conversation.item.patch.v3"
CONVERSATION_UI_PLAN_READY_V3 = "conversation.ui.plan_ready.v3"
CONVERSATION_UI_USER_INPUT_V3 = "conversation.ui.user_input.v3"
THREAD_LIFECYCLE_V3 = "thread.lifecycle.v3"
THREAD_ERROR_V3 = "thread.error.v3"

NODE_WORKFLOW_UPDATED = "node.workflow.updated"
NODE_DETAIL_INVALIDATE = "node.detail.invalidate"

TURN_STARTED = "turn_started"
WAITING_USER_INPUT = "waiting_user_input"
TURN_COMPLETED = "turn_completed"
TURN_FAILED = "turn_failed"
STREAM_MISMATCH = "stream_mismatch"
STREAM_SCHEMA_VERSION = 1
STREAM_OPEN = "stream_open"


def _coerce_iso_to_epoch_ms(value: str) -> int:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int(parsed.timestamp() * 1000))


def _extract_thread_id_from_payload(payload: dict[str, Any]) -> str | None:
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        thread_id = str(snapshot.get("threadId") or "").strip()
        if thread_id:
            return thread_id
    item = payload.get("item")
    if isinstance(item, dict):
        thread_id = str(item.get("threadId") or "").strip()
        if thread_id:
            return thread_id
    pending_requests = payload.get("activeUserInputRequests")
    if isinstance(pending_requests, list):
        for raw_request in pending_requests:
            if not isinstance(raw_request, dict):
                continue
            thread_id = str(raw_request.get("threadId") or "").strip()
            if thread_id:
                return thread_id
    return None


def _extract_turn_id_from_payload(payload: dict[str, Any]) -> str | None:
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        turn_id = str(snapshot.get("activeTurnId") or "").strip()
        if turn_id:
            return turn_id
    item = payload.get("item")
    if isinstance(item, dict):
        turn_id = str(item.get("turnId") or "").strip()
        if turn_id:
            return turn_id
    lifecycle_turn_id = str(payload.get("activeTurnId") or "").strip()
    if lifecycle_turn_id:
        return lifecycle_turn_id
    return None


def build_thread_envelope(
    *,
    project_id: str,
    node_id: str,
    thread_role: str,
    snapshot_version: int | None,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
    thread_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    occurred_at = iso_now()
    resolved_event_id = str(event_id or new_id("evt"))
    resolved_thread_id = str(thread_id or _extract_thread_id_from_payload(payload) or f"unbound::{thread_role}")
    resolved_turn_id = turn_id
    if resolved_turn_id is not None:
        resolved_turn_id = str(resolved_turn_id or "").strip() or None
    if resolved_turn_id is None:
        resolved_turn_id = _extract_turn_id_from_payload(payload)

    return {
        "schema_version": STREAM_SCHEMA_VERSION,
        "event_id": resolved_event_id,
        "event_type": event_type,
        "thread_id": resolved_thread_id,
        "turn_id": resolved_turn_id,
        "snapshot_version": snapshot_version,
        "occurred_at_ms": _coerce_iso_to_epoch_ms(occurred_at),
        "payload": payload,
        "eventId": resolved_event_id,
        "channel": THREAD_CHANNEL,
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": thread_role,
        "occurredAt": occurred_at,
        "snapshotVersion": snapshot_version,
        "type": event_type,
    }


def build_workflow_envelope(
    *,
    project_id: str,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "eventId": new_id("evt"),
        "channel": WORKFLOW_CHANNEL,
        "projectId": project_id,
        "nodeId": node_id,
        "occurredAt": iso_now(),
        "type": event_type,
        "payload": payload,
    }


def build_stream_open_envelope(
    *,
    project_id: str,
    node_id: str,
    thread_role: str,
    thread_id: str,
    snapshot_version: int | None,
    turn_id: str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    occurred_at = iso_now()
    merged_payload = dict(payload or {})
    return {
        "schema_version": STREAM_SCHEMA_VERSION,
        "event_type": STREAM_OPEN,
        "thread_id": thread_id,
        "turn_id": str(turn_id or "").strip() or None,
        "snapshot_version": snapshot_version,
        "occurred_at_ms": _coerce_iso_to_epoch_ms(occurred_at),
        "payload": merged_payload,
        "channel": THREAD_CHANNEL,
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": thread_role,
        "occurredAt": occurred_at,
        "snapshotVersion": snapshot_version,
        "type": STREAM_OPEN,
    }
