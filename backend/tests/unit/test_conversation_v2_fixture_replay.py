from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector import apply_raw_event


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


def _seed_snapshot():
    snapshot = default_thread_snapshot("project-1", "node-1", "ask_planning")
    snapshot["threadId"] = "thread_1"
    snapshot["activeTurnId"] = "turn_1"
    snapshot["processingState"] = "running"
    return snapshot


def _apply_sequence(snapshot: dict, entries: dict[str, dict], sequence: list[str]) -> tuple[dict, list[dict]]:
    current = copy.deepcopy(snapshot)
    emitted: list[dict] = []
    for event_class in sequence:
        fixture = entries[event_class]
        current, events = apply_raw_event(current, copy.deepcopy(fixture["payload"]))
        emitted.extend(events)
    return current, emitted


def test_phase0_raw_event_samples_are_replayable_and_non_template() -> None:
    entries = _load_fixture_entries()

    assert len(entries) >= 20
    assert all(entry["capture_status"] != "template" for entry in entries.values())
    assert all(isinstance(entry.get("payload"), dict) for entry in entries.values())


def test_phase0_fixture_replay_builds_deterministic_snapshot() -> None:
    entries = _load_fixture_entries()
    snapshot, emitted = _apply_sequence(
        _seed_snapshot(),
        entries,
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
        ],
    )

    assert snapshot["processingState"] == "idle"
    assert snapshot["activeTurnId"] is None
    assert [item["id"] for item in snapshot["items"]] == [
        "msg-1",
        "plan-1",
        "reason-1",
        "cmd-1",
        "file-1",
    ]

    assistant = next(item for item in snapshot["items"] if item["id"] == "msg-1")
    plan_item = next(item for item in snapshot["items"] if item["id"] == "plan-1")
    reasoning = next(item for item in snapshot["items"] if item["id"] == "reason-1")
    command_tool = next(item for item in snapshot["items"] if item["id"] == "cmd-1")
    file_tool = next(item for item in snapshot["items"] if item["id"] == "file-1")

    assert assistant["text"] == "hello"
    assert assistant["status"] == "completed"
    assert plan_item["text"] == "step 1"
    assert plan_item["status"] == "completed"
    assert reasoning["summaryText"] == "think"
    assert reasoning["status"] == "in_progress"
    assert command_tool["outputText"] == "stdout"
    assert command_tool["exitCode"] == 0
    assert command_tool["status"] == "completed"
    assert file_tool["outputFiles"] == [
        {"path": "final.txt", "changeType": "updated", "summary": "final"}
    ]
    assert file_tool["status"] == "completed"
    assert all(item["id"] != "tool-call:call-1" for item in snapshot["items"])
    assert emitted[-1]["type"] == event_types.THREAD_LIFECYCLE
    assert emitted[-1]["payload"]["state"] == event_types.TURN_COMPLETED


def test_phase0_fixture_replay_waiting_user_input_and_resolution() -> None:
    entries = _load_fixture_entries()

    waiting_snapshot, waiting_events = _apply_sequence(
        _seed_snapshot(),
        entries,
        ["user_input_requested", "turn_completed_waiting_user_input"],
    )

    assert waiting_snapshot["processingState"] == "waiting_user_input"
    assert waiting_snapshot["activeTurnId"] == "turn_1"
    assert waiting_snapshot["pendingRequests"] == [
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
    assert waiting_events[-1]["type"] == event_types.THREAD_LIFECYCLE
    assert waiting_events[-1]["payload"]["state"] == event_types.WAITING_USER_INPUT

    resolved_snapshot, resolved_events = _apply_sequence(
        waiting_snapshot,
        entries,
        ["user_input_resolved"],
    )

    user_input = next(item for item in resolved_snapshot["items"] if item["id"] == "input-1")
    assert user_input["status"] == "answered"
    assert user_input["answers"] == [
        {"questionId": "q1", "value": "a", "label": None}
    ]
    assert resolved_snapshot["pendingRequests"][0]["status"] == "answered"
    assert resolved_snapshot["pendingRequests"][0]["answers"] == [
        {"questionId": "q1", "value": "a", "label": None}
    ]
    assert resolved_events[-1]["type"] == event_types.CONVERSATION_REQUEST_USER_INPUT_RESOLVED


def test_phase0_fixture_replay_failed_turn_maps_to_turn_failed_lifecycle() -> None:
    entries = _load_fixture_entries()
    snapshot, emitted = _apply_sequence(
        _seed_snapshot(),
        entries,
        ["turn_completed_failed"],
    )

    assert snapshot["processingState"] == "idle"
    assert snapshot["activeTurnId"] is None
    assert emitted[-1]["type"] == event_types.THREAD_LIFECYCLE
    assert emitted[-1]["payload"]["state"] == event_types.TURN_FAILED
