from __future__ import annotations

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector import upsert_item
from backend.conversation.projector.thread_event_projector_v3 import (
    project_v2_envelope_to_v3,
    project_v2_snapshot_to_v3,
)


def test_v3_snapshot_projection_maps_execution_items_and_signals() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot_v2["threadId"] = "exec-thread-1"
    snapshot_v2, _ = upsert_item(
        snapshot_v2,
        {
            "id": "plan-1",
            "kind": "plan",
            "threadId": "exec-thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-01T00:00:00Z",
            "updatedAt": "2026-04-01T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "title": "Execution plan",
            "text": "Do the work",
            "steps": [{"id": "s1", "text": "step", "status": "completed"}],
        },
    )
    snapshot_v2["pendingRequests"] = [
        {
            "requestId": "req-1",
            "itemId": "input-1",
            "threadId": "exec-thread-1",
            "turnId": "turn-1",
            "status": "requested",
            "createdAt": "2026-04-01T00:01:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]

    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    assert snapshot_v3["lane"] == "execution"
    assert snapshot_v3["threadId"] == "exec-thread-1"
    assert [item["kind"] for item in snapshot_v3["items"]] == ["review"]
    assert snapshot_v3["uiSignals"]["planReady"] == {
        "planItemId": "plan-1",
        "revision": 1,
        "ready": True,
        "failed": False,
    }
    assert snapshot_v3["uiSignals"]["activeUserInputRequests"] == [
        {
            "requestId": "req-1",
            "itemId": "input-1",
            "threadId": "exec-thread-1",
            "turnId": "turn-1",
            "status": "requested",
            "createdAt": "2026-04-01T00:01:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]


def test_v3_projection_maps_upsert_and_patch_events() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "audit")
    snapshot_v2["threadId"] = "audit-thread-1"
    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    snapshot_v3, upsert_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_UPSERT,
            "payload": {
                "item": {
                    "id": "msg-1",
                    "kind": "message",
                    "threadId": "audit-thread-1",
                    "turnId": "turn-1",
                    "sequence": 1,
                    "createdAt": "2026-04-01T01:00:00Z",
                    "updatedAt": "2026-04-01T01:00:00Z",
                    "status": "in_progress",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "role": "assistant",
                    "text": "hello",
                    "format": "markdown",
                }
            },
        },
    )

    assert snapshot_v3["lane"] == "audit"
    assert snapshot_v3["items"][0]["kind"] == "message"
    assert upsert_events[0]["type"] == event_types.CONVERSATION_ITEM_UPSERT_V3
    assert upsert_events[0]["payload"]["item"]["id"] == "msg-1"

    snapshot_v3, patch_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "msg-1",
                "patch": {
                    "kind": "message",
                    "textAppend": " world",
                    "status": "completed",
                    "updatedAt": "2026-04-01T01:00:01Z",
                },
            },
        },
    )

    assert snapshot_v3["items"][0]["text"] == "hello world"
    assert snapshot_v3["items"][0]["status"] == "completed"
    assert patch_events[0]["type"] == event_types.CONVERSATION_ITEM_PATCH_V3


def test_v3_projection_emits_user_input_signal_events() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot_v2["threadId"] = "exec-thread-1"
    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    snapshot_v3, requested_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_REQUEST_USER_INPUT_REQUESTED,
            "payload": {
                "requestId": "req-1",
                "itemId": "input-1",
                "pendingRequest": {
                    "requestId": "req-1",
                    "itemId": "input-1",
                    "threadId": "exec-thread-1",
                    "turnId": "turn-1",
                    "status": "requested",
                    "createdAt": "2026-04-01T02:00:00Z",
                    "submittedAt": None,
                    "resolvedAt": None,
                    "answers": [],
                },
            },
        },
    )

    assert snapshot_v3["uiSignals"]["activeUserInputRequests"] == [
        {
            "requestId": "req-1",
            "itemId": "input-1",
            "threadId": "exec-thread-1",
            "turnId": "turn-1",
            "status": "requested",
            "createdAt": "2026-04-01T02:00:00Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]
    assert requested_events[-1]["type"] == event_types.CONVERSATION_UI_USER_INPUT_V3

    snapshot_v3, resolved_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_REQUEST_USER_INPUT_RESOLVED,
            "payload": {
                "requestId": "req-1",
                "itemId": "input-1",
                "status": "answered",
                "answers": [{"questionId": "q1", "value": "yes", "label": "Yes"}],
                "resolvedAt": "2026-04-01T02:01:00Z",
            },
        },
    )

    assert snapshot_v3["uiSignals"]["activeUserInputRequests"][0]["status"] == "answered"
    assert snapshot_v3["uiSignals"]["activeUserInputRequests"][0]["answers"] == [
        {"questionId": "q1", "value": "yes", "label": "Yes"}
    ]
    assert resolved_events[-1]["type"] == event_types.CONVERSATION_UI_USER_INPUT_V3


def test_v3_projection_maps_lifecycle_event() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    updated, events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.THREAD_LIFECYCLE,
            "payload": {
                "activeTurnId": "turn-7",
                "processingState": "running",
                "state": event_types.TURN_STARTED,
                "detail": "running",
            },
        },
    )

    assert updated["activeTurnId"] == "turn-7"
    assert updated["processingState"] == "running"
    assert events[0] == {
        "type": event_types.THREAD_LIFECYCLE_V3,
        "payload": {
            "activeTurnId": "turn-7",
            "processingState": "running",
            "state": event_types.TURN_STARTED,
            "detail": "running",
        },
    }
