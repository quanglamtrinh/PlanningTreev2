from __future__ import annotations

import pytest

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector import apply_raw_event, patch_item, upsert_item
from backend.errors.app_errors import ConversationStreamMismatch


def test_patch_missing_item_raises_stream_mismatch() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "ask_planning")

    with pytest.raises(ConversationStreamMismatch):
        patch_item(
            snapshot,
            "missing-item",
            {
                "kind": "message",
                "textAppend": "hello",
                "updatedAt": "2026-03-28T10:00:00Z",
            },
        )


def test_tool_output_files_replace_overrides_preview_append() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "ask_planning")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "tool-1",
            "kind": "tool",
            "threadId": "thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-03-28T10:00:00Z",
            "updatedAt": "2026-03-28T10:00:00Z",
            "status": "in_progress",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "toolType": "fileChange",
            "title": "file change",
            "toolName": "apply_patch",
            "callId": "call-1",
            "argumentsText": None,
            "outputText": "",
            "outputFiles": [],
            "exitCode": None,
        },
    )

    snapshot, _ = patch_item(
        snapshot,
        "tool-1",
        {
            "kind": "tool",
            "outputFilesAppend": [
                {"path": "preview.txt", "changeType": "created", "summary": "preview"}
            ],
            "updatedAt": "2026-03-28T10:00:01Z",
        },
    )
    snapshot, _ = patch_item(
        snapshot,
        "tool-1",
        {
            "kind": "tool",
            "outputFilesReplace": [
                {"path": "final.txt", "changeType": "updated", "summary": "final"}
            ],
            "status": "completed",
            "updatedAt": "2026-03-28T10:00:02Z",
        },
    )

    tool = snapshot["items"][0]
    assert tool["outputFiles"] == [
        {"path": "final.txt", "changeType": "updated", "summary": "final"}
    ]
    assert tool["status"] == "completed"


def test_turn_completed_finalizes_open_items_for_active_turn() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "ask_planning")
    snapshot["threadId"] = "thread-1"
    snapshot["activeTurnId"] = "turn-1"
    snapshot["processingState"] = "running"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "reason-1",
            "kind": "reasoning",
            "threadId": "thread-1",
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-03-28T10:00:00Z",
            "updatedAt": "2026-03-28T10:00:00Z",
            "status": "in_progress",
            "source": "upstream",
            "tone": "muted",
            "metadata": {},
            "summaryText": "thinking",
            "detailText": None,
        },
    )

    updated, events = apply_raw_event(
        snapshot,
        {
            "method": "turn/completed",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "params": {"turn": {"id": "turn-1", "status": "completed"}},
        },
    )

    reasoning = updated["items"][0]
    assert reasoning["status"] == "completed"
    assert updated["processingState"] == "idle"
    assert updated["activeTurnId"] is None
    assert events[-1]["type"] == event_types.THREAD_LIFECYCLE
    assert events[-1]["payload"]["state"] == event_types.TURN_COMPLETED


def test_thread_status_changed_maps_to_canonical_lifecycle_state() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "ask_planning")
    snapshot["threadId"] = "thread-1"
    snapshot["activeTurnId"] = "turn-1"
    snapshot["processingState"] = "running"

    updated, events = apply_raw_event(
        snapshot,
        {
            "method": "thread/status/changed",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "params": {"status": {"type": "running"}},
        },
    )

    assert updated["processingState"] == "running"
    assert updated["activeTurnId"] == "turn-1"
    assert events == [
        {
            "type": event_types.THREAD_LIFECYCLE,
            "payload": {
                "activeTurnId": "turn-1",
                "processingState": "running",
                "state": event_types.TURN_STARTED,
                "detail": "running",
            },
        }
    ]


def test_upsert_existing_item_preserves_sequence_and_created_at() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "audit")
    snapshot["threadId"] = "audit-thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "audit-record:frame",
            "kind": "message",
            "threadId": "audit-thread-1",
            "turnId": None,
            "sequence": 3,
            "createdAt": "2026-03-28T10:00:00Z",
            "updatedAt": "2026-03-28T10:00:00Z",
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {},
            "role": "system",
            "text": "original",
            "format": "markdown",
        },
    )

    updated, events = upsert_item(
        snapshot,
        {
            "id": "audit-record:frame",
            "kind": "message",
            "threadId": "audit-thread-1",
            "turnId": None,
            "sequence": 99,
            "createdAt": "2030-01-01T00:00:00Z",
            "updatedAt": "2026-03-28T10:05:00Z",
            "status": "completed",
            "source": "backend",
            "tone": "success",
            "metadata": {"reconfirmed": True},
            "role": "system",
            "text": "updated",
            "format": "markdown",
        },
    )

    item = updated["items"][0]
    assert item["sequence"] == 3
    assert item["createdAt"] == "2026-03-28T10:00:00Z"
    assert item["updatedAt"] == "2026-03-28T10:05:00Z"
    assert item["text"] == "updated"
    assert events[0]["payload"]["item"]["sequence"] == 3
    assert events[0]["payload"]["item"]["createdAt"] == "2026-03-28T10:00:00Z"


def test_upsert_existing_item_raises_on_immutable_field_drift() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "audit")
    snapshot["threadId"] = "audit-thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "audit-record:frame",
            "kind": "message",
            "threadId": "audit-thread-1",
            "turnId": None,
            "sequence": 1,
            "createdAt": "2026-03-28T10:00:00Z",
            "updatedAt": "2026-03-28T10:00:00Z",
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {},
            "role": "system",
            "text": "original",
            "format": "markdown",
        },
    )

    with pytest.raises(ConversationStreamMismatch):
        upsert_item(
            snapshot,
            {
                "id": "audit-record:frame",
                "kind": "message",
                "threadId": "audit-thread-1",
                "turnId": "turn-1",
                "sequence": 2,
                "createdAt": "2026-03-28T10:01:00Z",
                "updatedAt": "2026-03-28T10:01:00Z",
                "status": "completed",
                "source": "backend",
                "tone": "neutral",
                "metadata": {},
                "role": "system",
                "text": "updated",
                "format": "markdown",
            },
        )
