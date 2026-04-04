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
    assert tool["changes"] == [
        {"path": "final.txt", "kind": "modify", "diff": None, "summary": "final"}
    ]
    assert tool["status"] == "completed"


def test_file_change_completed_replace_preserves_kind_and_diff() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "file-tool-1",
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
            "callId": None,
            "argumentsText": None,
            "outputText": "",
            "outputFiles": [],
            "exitCode": None,
        },
    )

    snapshot, _ = apply_raw_event(
        snapshot,
        {
            "method": "item/fileChange/outputDelta",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "file-tool-1",
            "params": {
                "files": [
                    {"path": "preview.txt", "changeType": "created", "summary": "preview"},
                ]
            },
        },
    )
    snapshot, _ = apply_raw_event(
        snapshot,
        {
            "method": "item/completed",
            "received_at": "2026-03-28T10:00:02Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "file-tool-1",
            "params": {
                "item": {
                    "id": "file-tool-1",
                    "type": "fileChange",
                    "changes": [
                        {
                            "path": "src/main.ts",
                            "kind": "add",
                            "summary": "new file",
                            "diff": "@@ -0,0 +1 @@\n+console.log('ok')\n",
                        }
                    ],
                }
            },
        },
    )

    tool = snapshot["items"][0]
    assert tool["status"] == "completed"
    assert tool["callId"] is None
    assert tool["changes"] == [
        {
            "path": "src/main.ts",
            "kind": "add",
            "summary": "new file",
            "diff": "@@ -0,0 +1 @@\n+console.log('ok')\n",
        }
    ]
    assert tool["outputFiles"] == [
        {
            "path": "src/main.ts",
            "changeType": "created",
            "summary": "new file",
            "diff": "@@ -0,0 +1 @@\n+console.log('ok')\n",
        }
    ]


def test_file_change_completed_explicit_empty_changes_replaces_preview() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "file-tool-2",
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
            "callId": "call-2",
            "argumentsText": None,
            "outputText": "",
            "outputFiles": [],
            "exitCode": None,
        },
    )
    snapshot, _ = patch_item(
        snapshot,
        "file-tool-2",
        {
            "kind": "tool",
            "outputFilesAppend": [
                {"path": "preview.txt", "changeType": "created", "summary": "preview"}
            ],
            "updatedAt": "2026-03-28T10:00:01Z",
        },
    )

    snapshot, _ = apply_raw_event(
        snapshot,
        {
            "method": "item/completed",
            "received_at": "2026-03-28T10:00:02Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "file-tool-2",
            "params": {"item": {"id": "file-tool-2", "type": "fileChange", "changes": []}},
        },
    )

    tool = snapshot["items"][0]
    assert tool["changes"] == []
    assert tool["outputFiles"] == []


def test_tool_patch_changes_append_respects_explicit_empty_changes_without_falling_back_to_output_files() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "file-tool-empty-canonical",
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
            "callId": "call-empty",
            "argumentsText": None,
            "outputText": "",
            "outputFiles": [
                {"path": "stale.txt", "changeType": "updated", "summary": "stale"},
            ],
            "changes": [],
            "exitCode": None,
        },
    )
    # Simulate canonical-empty state drift from persisted snapshots:
    # keep legacy outputFiles but force canonical changes to explicit empty.
    snapshot["items"][0]["changes"] = []

    snapshot, _ = patch_item(
        snapshot,
        "file-tool-empty-canonical",
        {
            "kind": "tool",
            "changesAppend": [
                {
                    "path": "canonical.txt",
                    "kind": "add",
                    "summary": "canonical",
                    "diff": "@@ -0,0 +1 @@\n+ok\n",
                }
            ],
            "updatedAt": "2026-03-28T10:00:01Z",
        },
    )

    tool = snapshot["items"][0]
    assert tool["changes"] == [
        {
            "path": "canonical.txt",
            "kind": "add",
            "summary": "canonical",
            "diff": "@@ -0,0 +1 @@\n+ok\n",
        }
    ]
    assert tool["outputFiles"] == [
        {
            "path": "canonical.txt",
            "changeType": "created",
            "summary": "canonical",
            "diff": "@@ -0,0 +1 @@\n+ok\n",
        }
    ]


def test_file_change_completed_without_changes_keeps_preview_data() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "file-tool-3",
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
            "callId": "call-3",
            "argumentsText": None,
            "outputText": "",
            "outputFiles": [],
            "exitCode": None,
        },
    )
    snapshot, _ = apply_raw_event(
        snapshot,
        {
            "method": "item/fileChange/outputDelta",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "file-tool-3",
            "params": {
                "files": [
                    {"path": "preview.txt", "changeType": "created", "summary": "preview"},
                ]
            },
        },
    )
    snapshot, _ = apply_raw_event(
        snapshot,
        {
            "method": "item/completed",
            "received_at": "2026-03-28T10:00:02Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "file-tool-3",
            "params": {"item": {"id": "file-tool-3", "type": "fileChange"}},
        },
    )

    tool = snapshot["items"][0]
    assert tool["outputFiles"] == [
        {"path": "preview.txt", "changeType": "created", "summary": "preview"}
    ]
    assert tool["changes"] == [
        {"path": "preview.txt", "kind": "add", "diff": None, "summary": "preview"}
    ]


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


def test_terminal_interaction_appends_stdin_block_in_receive_order() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread-1"
    snapshot, _ = upsert_item(
        snapshot,
        {
            "id": "cmd-1",
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
            "toolType": "commandExecution",
            "title": "cmd",
            "toolName": "powershell",
            "callId": "call-1",
            "argumentsText": None,
            "outputText": "stdout line",
            "outputFiles": [],
            "exitCode": None,
        },
    )

    updated, events = apply_raw_event(
        snapshot,
        {
            "method": "item/commandExecution/terminalInteraction",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "item_id": "cmd-1",
            "request_id": None,
            "call_id": None,
            "params": {"stdin": "y\r\n"},
        },
    )

    tool = updated["items"][0]
    assert tool["outputText"] == "stdout line\n[stdin]\ny\n"
    assert tool["status"] == "in_progress"
    assert events == [
        {
            "type": event_types.CONVERSATION_ITEM_PATCH,
            "payload": {
                "itemId": "cmd-1",
                "patch": {
                    "kind": "tool",
                    "outputTextAppend": "\n[stdin]\ny\n",
                    "status": "in_progress",
                    "updatedAt": "2026-03-28T10:00:01Z",
                },
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
