from __future__ import annotations

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
NODE_WORKFLOW_UPDATED = "node.workflow.updated"
NODE_DETAIL_INVALIDATE = "node.detail.invalidate"

TURN_STARTED = "turn_started"
WAITING_USER_INPUT = "waiting_user_input"
TURN_COMPLETED = "turn_completed"
TURN_FAILED = "turn_failed"
STREAM_MISMATCH = "stream_mismatch"


def build_thread_envelope(
    *,
    project_id: str,
    node_id: str,
    thread_role: str,
    snapshot_version: int | None,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "eventId": new_id("evt"),
        "channel": THREAD_CHANNEL,
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": thread_role,
        "occurredAt": iso_now(),
        "snapshotVersion": snapshot_version,
        "type": event_type,
        "payload": payload,
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
