from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector import apply_raw_event
from backend.conversation.projector.thread_event_projector_v3 import (
    project_v2_envelope_to_v3,
    project_v2_snapshot_to_v3,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "handoff"
    / "conversation-streaming-v2"
    / "artifacts"
    / "phase-0"
    / "raw-event-samples.jsonl"
)


def _load_fixture_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        entries[str(payload["event_class"])] = payload
    return entries


def _seed_snapshot_v2():
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "thread_1"
    snapshot["activeTurnId"] = "turn_1"
    snapshot["processingState"] = "running"
    return snapshot


def _apply_sequence_to_v3(sequence: list[str]) -> tuple[dict, list[dict]]:
    entries = _load_fixture_entries()
    v2_snapshot = _seed_snapshot_v2()
    v3_snapshot = project_v2_snapshot_to_v3(v2_snapshot)
    emitted_v3: list[dict] = []

    for event_class in sequence:
        fixture = entries[event_class]
        v2_snapshot, emitted_v2 = apply_raw_event(v2_snapshot, copy.deepcopy(fixture["payload"]))
        for event in emitted_v2:
            v3_snapshot, mapped_events = project_v2_envelope_to_v3(v3_snapshot, event)
            emitted_v3.extend(mapped_events)
    return v3_snapshot, emitted_v3


def test_v3_fixture_replay_builds_deterministic_snapshot() -> None:
    snapshot, emitted = _apply_sequence_to_v3(
        [
            "agent_message_started",
            "agent_message_delta",
            "agent_message_completed",
            "plan_started",
            "plan_delta",
            "plan_completed",
            "reasoning_event",
            "command_started",
            "command_output_delta",
            "command_completed",
            "file_change_started",
            "file_change_delta",
            "file_change_completed",
            "raw_tool_call",
            "thread_status_changed",
            "turn_completed_success",
        ]
    )

    assert snapshot["lane"] == "execution"
    assert snapshot["processingState"] == "idle"
    assert snapshot["activeTurnId"] is None
    assert [item["id"] for item in snapshot["items"]] == [
        "msg-1",
        "plan-1",
        "reason-1",
        "cmd-1",
        "file-1",
    ]
    assert [item["kind"] for item in snapshot["items"]] == [
        "message",
        "review",
        "reasoning",
        "tool",
        "tool",
    ]
    assert snapshot["uiSignals"]["planReady"]["ready"] is True
    assert snapshot["uiSignals"]["planReady"]["planItemId"] == "plan-1"
    assert emitted[-1]["type"] in {
        event_types.THREAD_LIFECYCLE_V3,
        event_types.CONVERSATION_UI_PLAN_READY_V3,
    }


def test_v3_fixture_replay_waiting_user_input_and_resolution() -> None:
    waiting_snapshot, waiting_events = _apply_sequence_to_v3(
        ["user_input_requested", "turn_completed_waiting_user_input"]
    )

    assert waiting_snapshot["processingState"] == "waiting_user_input"
    assert waiting_snapshot["activeTurnId"] == "turn_1"
    assert waiting_snapshot["uiSignals"]["activeUserInputRequests"] == [
        {
            "requestId": "55",
            "itemId": "input-1",
            "threadId": "thread_1",
            "turnId": "turn_1",
            "status": "requested",
            "createdAt": "2026-03-28T10:00:15Z",
            "submittedAt": None,
            "resolvedAt": None,
            "answers": [],
        }
    ]
    assert any(event["type"] == event_types.CONVERSATION_UI_USER_INPUT_V3 for event in waiting_events)

    resolved_snapshot, resolved_events = _apply_sequence_to_v3(
        ["user_input_requested", "turn_completed_waiting_user_input", "user_input_resolved"]
    )

    assert resolved_snapshot["uiSignals"]["activeUserInputRequests"][0]["status"] == "answered"
    assert resolved_snapshot["uiSignals"]["activeUserInputRequests"][0]["answers"] == [
        {"questionId": "q1", "value": "a", "label": None}
    ]
    assert any(event["type"] == event_types.CONVERSATION_UI_USER_INPUT_V3 for event in resolved_events)

