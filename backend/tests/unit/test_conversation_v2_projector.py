from __future__ import annotations

import pytest

from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector import patch_item, upsert_item
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
