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


def _default_fixture_entries() -> dict[str, dict]:
    return {
        "agent_message_started": {
            "event_class": "agent_message_started",
            "payload": {
                "method": "item/started",
                "received_at": "2026-03-28T10:00:01Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "msg-1",
                "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
            },
        },
        "agent_message_delta": {
            "event_class": "agent_message_delta",
            "payload": {
                "method": "item/agentMessage/delta",
                "received_at": "2026-03-28T10:00:02Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "msg-1",
                "params": {"delta": "hello"},
            },
        },
        "agent_message_completed": {
            "event_class": "agent_message_completed",
            "payload": {
                "method": "item/completed",
                "received_at": "2026-03-28T10:00:03Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "msg-1",
                "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
            },
        },
        "plan_started": {
            "event_class": "plan_started",
            "payload": {
                "method": "item/started",
                "received_at": "2026-03-28T10:00:04Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "plan-1",
                "params": {"item": {"type": "plan", "id": "plan-1"}},
            },
        },
        "plan_delta": {
            "event_class": "plan_delta",
            "payload": {
                "method": "item/plan/delta",
                "received_at": "2026-03-28T10:00:05Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "plan-1",
                "params": {"delta": "Do the work"},
            },
        },
        "plan_completed": {
            "event_class": "plan_completed",
            "payload": {
                "method": "item/completed",
                "received_at": "2026-03-28T10:00:06Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "plan-1",
                "params": {"item": {"type": "plan", "id": "plan-1"}},
            },
        },
        "reasoning_event": {
            "event_class": "reasoning_event",
            "payload": {
                "method": "item/reasoning/summaryDelta",
                "received_at": "2026-03-28T10:00:07Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "reason-1",
                "params": {"delta": "Reasoning"},
            },
        },
        "command_started": {
            "event_class": "command_started",
            "payload": {
                "method": "item/started",
                "received_at": "2026-03-28T10:00:08Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "cmd-1",
                "params": {"item": {"type": "commandExecution", "id": "cmd-1", "command": "echo hi"}},
            },
        },
        "command_output_delta": {
            "event_class": "command_output_delta",
            "payload": {
                "method": "item/commandExecution/outputDelta",
                "received_at": "2026-03-28T10:00:09Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "cmd-1",
                "params": {"delta": "ok"},
            },
        },
        "command_completed": {
            "event_class": "command_completed",
            "payload": {
                "method": "item/completed",
                "received_at": "2026-03-28T10:00:10Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "cmd-1",
                "params": {"item": {"type": "commandExecution", "id": "cmd-1", "exitCode": 0}},
            },
        },
        "file_change_started": {
            "event_class": "file_change_started",
            "payload": {
                "method": "item/started",
                "received_at": "2026-03-28T10:00:11Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "file-1",
                "params": {"item": {"type": "fileChange", "id": "file-1", "callId": "call-1"}},
            },
        },
        "file_change_delta": {
            "event_class": "file_change_delta",
            "payload": {
                "method": "item/fileChange/outputDelta",
                "received_at": "2026-03-28T10:00:12Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "file-1",
                "params": {
                    "delta": "preview",
                    "files": [{"path": "preview.txt", "changeType": "created", "summary": "preview"}],
                },
            },
        },
        "file_change_completed": {
            "event_class": "file_change_completed",
            "payload": {
                "method": "item/completed",
                "received_at": "2026-03-28T10:00:13Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "file-1",
                "params": {
                    "item": {
                        "type": "fileChange",
                        "id": "file-1",
                        "changes": [{"path": "final.txt", "changeType": "updated", "summary": "final"}],
                    }
                },
            },
        },
        "raw_tool_call": {
            "event_class": "raw_tool_call",
            "payload": {
                "method": "item/tool/call",
                "received_at": "2026-03-28T10:00:14Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "call_id": "call-1",
                "params": {"tool_name": "apply_patch", "arguments": {"path": "file.txt"}},
            },
        },
        "thread_status_changed": {
            "event_class": "thread_status_changed",
            "payload": {
                "method": "thread/status/changed",
                "received_at": "2026-03-28T10:00:15Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "params": {"status": {"type": "running"}},
            },
        },
        "turn_completed_success": {
            "event_class": "turn_completed_success",
            "payload": {
                "method": "turn/completed",
                "received_at": "2026-03-28T10:00:16Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "params": {"turn": {"status": "completed", "id": "turn_1"}},
            },
        },
        "user_input_requested": {
            "event_class": "user_input_requested",
            "payload": {
                "method": "item/tool/requestUserInput",
                "received_at": "2026-03-28T10:00:15Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "input-1",
                "request_id": "55",
                "params": {"questions": [{"id": "q1", "prompt": "Q1", "inputType": "text", "options": []}]},
            },
        },
        "turn_completed_waiting_user_input": {
            "event_class": "turn_completed_waiting_user_input",
            "payload": {
                "method": "turn/completed",
                "received_at": "2026-03-28T10:00:16Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "params": {"turn": {"status": "waiting_user_input", "id": "turn_1"}},
            },
        },
        "user_input_resolved": {
            "event_class": "user_input_resolved",
            "payload": {
                "method": "serverRequest/resolved",
                "received_at": "2026-03-28T10:00:17Z",
                "thread_id": "thread_1",
                "turn_id": "turn_1",
                "item_id": "input-1",
                "request_id": "55",
                "params": {"answers": {"q1": "a"}, "resolved_at": "2026-03-28T10:00:17Z"},
            },
        },
    }


def _load_fixture_entries() -> dict[str, dict]:
    if not FIXTURE_PATH.exists():
        return _default_fixture_entries()
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

    assert snapshot["threadRole"] == "execution"
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
        "diff",
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
