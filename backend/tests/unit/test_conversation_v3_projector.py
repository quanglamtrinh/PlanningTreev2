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


def test_v3_snapshot_projection_maps_ask_planning_to_ask_lane() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "ask_planning")
    snapshot_v2["threadId"] = "ask-thread-1"

    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    assert snapshot_v3["lane"] == "ask"
    assert snapshot_v3["threadId"] == "ask-thread-1"


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


def test_v3_projection_semantics_cover_review_explore_diff_and_patch_kind_mapping() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot_v2["threadId"] = "exec-thread-1"
    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    snapshot_v3, review_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_UPSERT,
            "payload": {
                "item": {
                    "id": "review-msg-1",
                    "kind": "message",
                    "threadId": "exec-thread-1",
                    "turnId": "turn-1",
                    "sequence": 1,
                    "createdAt": "2026-04-01T01:00:00Z",
                    "updatedAt": "2026-04-01T01:00:00Z",
                    "status": "in_progress",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {"workflowReviewSummary": True},
                    "role": "assistant",
                    "text": "Review summary text",
                    "format": "markdown",
                }
            },
        },
    )
    assert review_events[0]["payload"]["item"]["kind"] == "review"
    assert review_events[0]["payload"]["item"]["metadata"]["semanticKind"] == "workflowReviewSummary"
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["review-msg-1"]["kind"] == "review"

    snapshot_v3, review_patch_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "review-msg-1",
                "patch": {
                    "kind": "message",
                    "textAppend": " appended",
                    "status": "completed",
                    "updatedAt": "2026-04-01T01:00:01Z",
                },
            },
        },
    )
    assert review_patch_events[0]["type"] == event_types.CONVERSATION_ITEM_PATCH_V3
    assert review_patch_events[0]["payload"]["patch"]["kind"] == "review"
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["review-msg-1"]["text"] == "Review summary text appended"

    snapshot_v3, explore_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_UPSERT,
            "payload": {
                "item": {
                    "id": "explore-msg-1",
                    "kind": "message",
                    "threadId": "exec-thread-1",
                    "turnId": None,
                    "sequence": 2,
                    "createdAt": "2026-04-01T01:00:02Z",
                    "updatedAt": "2026-04-01T01:00:02Z",
                    "status": "completed",
                    "source": "backend",
                    "tone": "neutral",
                    "metadata": {"workflowReviewGuidance": True},
                    "role": "system",
                    "text": "Guidance content",
                    "format": "markdown",
                }
            },
        },
    )
    assert explore_events[0]["payload"]["item"]["kind"] == "explore"
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["explore-msg-1"]["kind"] == "explore"

    snapshot_v3, explore_patch_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "explore-msg-1",
                "patch": {
                    "kind": "message",
                    "textAppend": " plus",
                    "status": "completed",
                    "updatedAt": "2026-04-01T01:00:03Z",
                },
            },
        },
    )
    assert explore_patch_events[0]["payload"]["patch"]["kind"] == "explore"
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["explore-msg-1"]["text"] == "Guidance content plus"

    snapshot_v3, diff_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_UPSERT,
            "payload": {
                "item": {
                    "id": "file-tool-1",
                    "kind": "tool",
                    "threadId": "exec-thread-1",
                    "turnId": "turn-2",
                    "sequence": 3,
                    "createdAt": "2026-04-01T01:00:04Z",
                    "updatedAt": "2026-04-01T01:00:04Z",
                    "status": "in_progress",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "toolType": "fileChange",
                    "title": "Apply patch",
                    "toolName": "apply_patch",
                    "callId": "call-1",
                    "argumentsText": None,
                    "outputText": "Summary",
                    "changes": [
                        {
                            "path": "src/main.ts",
                            "kind": "modify",
                            "summary": "core update",
                            "diff": "@@ -1 +1 @@\n-old\n+new\n",
                        }
                    ],
                    "outputFiles": [
                        {
                            "path": "src/main.ts",
                            "changeType": "updated",
                            "summary": "core update",
                        }
                    ],
                    "exitCode": None,
                }
            },
        },
    )
    assert diff_events[0]["payload"]["item"]["kind"] == "diff"
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["file-tool-1"]["kind"] == "diff"
    assert snapshot_items_by_id["file-tool-1"]["changes"] == [
        {
            "path": "src/main.ts",
            "kind": "modify",
            "summary": "core update",
            "diff": "@@ -1 +1 @@\n-old\n+new\n",
        }
    ]
    assert snapshot_items_by_id["file-tool-1"]["files"] == [
        {
            "path": "src/main.ts",
            "changeType": "updated",
            "summary": "core update",
            "patchText": "@@ -1 +1 @@\n-old\n+new\n",
        }
    ]

    snapshot_v3, diff_patch_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "file-tool-1",
                "patch": {
                    "kind": "tool",
                    "outputTextAppend": " delta",
                    "changesAppend": [
                        {
                            "path": "src/new.ts",
                            "kind": "add",
                            "summary": "new file",
                            "diff": "@@ -0,0 +1 @@\n+export const v = 1\n",
                        }
                    ],
                    "status": "completed",
                    "updatedAt": "2026-04-01T01:00:05Z",
                },
            },
        },
    )
    assert diff_patch_events[0]["payload"]["patch"]["kind"] == "diff"
    assert diff_patch_events[0]["payload"]["patch"]["changesAppend"] == [
        {
            "path": "src/new.ts",
            "kind": "add",
            "summary": "new file",
            "diff": "@@ -0,0 +1 @@\n+export const v = 1\n",
        }
    ]
    snapshot_items_by_id = {item["id"]: item for item in snapshot_v3["items"]}
    assert snapshot_items_by_id["file-tool-1"]["summaryText"] == "Summary delta"
    assert snapshot_items_by_id["file-tool-1"]["changes"] == [
        {
            "path": "src/main.ts",
            "kind": "modify",
            "summary": "core update",
            "diff": "@@ -1 +1 @@\n-old\n+new\n",
        },
        {
            "path": "src/new.ts",
            "kind": "add",
            "summary": "new file",
            "diff": "@@ -0,0 +1 @@\n+export const v = 1\n",
        },
    ]
    assert snapshot_items_by_id["file-tool-1"]["files"] == [
        {
            "path": "src/main.ts",
            "changeType": "updated",
            "summary": "core update",
            "patchText": "@@ -1 +1 @@\n-old\n+new\n",
        },
        {
            "path": "src/new.ts",
            "changeType": "created",
            "summary": "new file",
            "patchText": "@@ -0,0 +1 @@\n+export const v = 1\n",
        },
    ]


def test_v3_diff_patch_changes_replace_authoritative_empty() -> None:
    snapshot_v2 = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot_v2["threadId"] = "exec-thread-1"
    snapshot_v3 = project_v2_snapshot_to_v3(snapshot_v2)

    snapshot_v3, _ = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_UPSERT,
            "payload": {
                "item": {
                    "id": "file-tool-2",
                    "kind": "tool",
                    "threadId": "exec-thread-1",
                    "turnId": "turn-3",
                    "sequence": 1,
                    "createdAt": "2026-04-01T01:00:00Z",
                    "updatedAt": "2026-04-01T01:00:00Z",
                    "status": "in_progress",
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": {},
                    "toolType": "fileChange",
                    "title": "Apply patch",
                    "toolName": "apply_patch",
                    "callId": "call-2",
                    "argumentsText": None,
                    "outputText": "",
                    "changes": [{"path": "preview.txt", "kind": "add", "summary": "preview", "diff": None}],
                    "outputFiles": [{"path": "preview.txt", "changeType": "created", "summary": "preview"}],
                    "exitCode": None,
                }
            },
        },
    )

    snapshot_v3, patch_events = project_v2_envelope_to_v3(
        snapshot_v3,
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "file-tool-2",
                "patch": {
                    "kind": "tool",
                    "changesReplace": [],
                    "outputFilesReplace": [],
                    "status": "completed",
                    "updatedAt": "2026-04-01T01:00:01Z",
                },
            },
        },
    )

    assert patch_events[0]["payload"]["patch"]["kind"] == "diff"
    assert patch_events[0]["payload"]["patch"]["changesReplace"] == []
    assert patch_events[0]["payload"]["patch"]["filesReplace"] == []
    item = {current["id"]: current for current in snapshot_v3["items"]}["file-tool-2"]
    assert item["changes"] == []
    assert item["files"] == []
