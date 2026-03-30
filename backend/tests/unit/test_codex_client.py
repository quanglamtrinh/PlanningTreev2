from __future__ import annotations

import logging
from typing import Any

from backend.ai.codex_client import StdioTransport


def test_send_prompt_streaming_uses_internal_turn_helper_without_reentering_public_run_turn(
    monkeypatch,
) -> None:
    transport = StdioTransport()
    rpc_calls: list[str] = []

    monkeypatch.setattr(transport, "is_alive", lambda: True)
    monkeypatch.setattr(transport, "_initialize_session", lambda timeout_sec: None)

    def fake_rpc(method: str, params: dict[str, object], timeout: int = 30) -> dict[str, object]:
        rpc_calls.append(method)
        if method == "thread/start":
            return {"thread": {"id": "thread_1"}}
        if method == "turn/start":
            return {"turn": {"id": "turn_1"}}
        raise AssertionError(f"Unexpected RPC: {method}")

    monkeypatch.setattr(transport, "_rpc", fake_rpc)
    monkeypatch.setattr(transport, "_wait_for_turn_result", lambda turn_id, timeout_sec: ("ok", []))
    monkeypatch.setattr(
        transport,
        "run_turn_streaming",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("send_prompt_streaming should not call public run_turn_streaming")
        ),
    )

    response = transport.send_prompt_streaming("hello")

    assert response == {
        "stdout": "ok",
        "thread_id": "thread_1",
        "turn_id": "turn_1",
        "tool_calls": [],
        "turn_status": None,
        "final_plan_item": None,
        "runtime_request_ids": [],
    }
    assert rpc_calls == ["thread/start", "turn/start"]


def test_send_prompt_streaming_forwards_optional_plan_delta_callback(monkeypatch) -> None:
    transport = StdioTransport()
    captured: dict[str, object] = {}

    monkeypatch.setattr(transport, "is_alive", lambda: True)

    def fake_send_prompt_modern(prompt: str, **kwargs: object) -> dict[str, object]:
        captured["prompt"] = prompt
        captured.update(kwargs)
        return {
            "stdout": "ok",
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "tool_calls": [],
            "turn_status": None,
            "final_plan_item": None,
            "runtime_request_ids": [],
        }

    monkeypatch.setattr(transport, "_send_prompt_modern", fake_send_prompt_modern)

    callback = lambda delta, item: None
    response = transport.send_prompt_streaming("hello", on_plan_delta=callback)

    assert response["stdout"] == "ok"
    assert captured["prompt"] == "hello"
    assert captured["on_plan_delta"] is callback


def test_codex_app_client_run_turn_streaming_forwards_on_raw_event(monkeypatch) -> None:
    from backend.ai.codex_client import CodexAppClient

    transport = StdioTransport()
    client = CodexAppClient(transport)
    client._started = True
    monkeypatch.setattr(transport, "is_alive", lambda: True)

    captured: dict[str, object] = {}

    def fake_run_turn_streaming(prompt: str, **kwargs: object) -> dict[str, object]:
        captured["prompt"] = prompt
        captured.update(kwargs)
        return {"stdout": "ok", "thread_id": str(kwargs.get("thread_id") or "")}

    monkeypatch.setattr(transport, "run_turn_streaming", fake_run_turn_streaming)

    callback = lambda payload: None
    response = client.run_turn_streaming(
        "hello",
        thread_id="thread_1",
        on_raw_event=callback,
    )

    assert response["stdout"] == "ok"
    assert captured["prompt"] == "hello"
    assert captured["on_raw_event"] is callback


def test_item_started_and_completed_emit_item_callback() -> None:
    transport = StdioTransport()
    seen: list[tuple[str, dict[str, object]]] = []
    raw_seen: list[dict[str, object]] = []
    state = transport._get_turn_state("turn_1")
    state.on_item_event = lambda phase, item: seen.append((phase, item))
    state.on_raw_event = raw_seen.append
    state.callbacks_attached = True

    command_item = {
        "type": "commandExecution",
        "id": "call-1",
        "command": "dir",
        "status": "inProgress",
    }
    transport._handle_notification(
        "item/started",
        {"turnId": "turn_1", "item": command_item},
    )
    transport._handle_notification(
        "item/completed",
        {"turnId": "turn_1", "threadId": "thread_1", "item": {**command_item, "status": "completed"}},
    )

    assert seen == [
        ("started", command_item),
        ("completed", {**command_item, "status": "completed"}),
    ]
    assert [event["method"] for event in raw_seen] == ["item/started", "item/completed"]
    assert raw_seen[0]["item_id"] == "call-1"
    assert raw_seen[1]["item_id"] == "call-1"


def test_global_account_notifications_do_not_break_turn_scoped_notifications() -> None:
    transport = StdioTransport()
    account_updates: list[dict[str, object]] = []
    rate_limit_updates: list[dict[str, object]] = []
    deltas: list[str] = []
    raw_events: list[dict[str, object]] = []

    transport.add_account_updated_listener(account_updates.append)
    transport.add_rate_limits_updated_listener(rate_limit_updates.append)

    state = transport._get_turn_state("turn_1")
    state.on_delta = deltas.append
    state.on_raw_event = raw_events.append
    state.callbacks_attached = True

    transport._handle_notification("account/updated", {"authMode": "chatgpt"})
    transport._handle_notification(
        "account/rateLimits/updated",
        {"rateLimits": {"primary": {"usedPercent": 10}}},
    )
    transport._handle_notification(
        "item/agentMessage/delta",
        {"turnId": "turn_1", "itemId": "msg-1", "delta": "hello"},
    )

    assert account_updates == [{"authMode": "chatgpt"}]
    assert rate_limit_updates == [{"rateLimits": {"primary": {"usedPercent": 10}}}]
    assert deltas == ["hello"]
    assert raw_events == [
        {
            "method": "item/agentMessage/delta",
            "received_at": raw_events[0]["received_at"],
            "thread_id": None,
            "turn_id": "turn_1",
            "item_id": "msg-1",
            "request_id": None,
            "call_id": None,
            "params": {"turnId": "turn_1", "itemId": "msg-1", "delta": "hello"},
        }
    ]


def test_send_prompt_streaming_preserves_early_turn_completion_state(monkeypatch) -> None:
    transport = StdioTransport()

    monkeypatch.setattr(transport, "is_alive", lambda: True)
    monkeypatch.setattr(transport, "_initialize_session", lambda timeout_sec: None)

    def fake_rpc(method: str, params: dict[str, object], timeout: int = 30) -> dict[str, object]:
        if method == "thread/start":
            return {"thread": {"id": "thread_1"}}
        if method == "turn/start":
            state = transport._get_turn_state("turn_1")
            state.stdout_parts.append("early result")
            state.tool_calls.append({"tool_name": "emit_spec_content", "arguments": {"content": "# Spec"}})
            state.turn_status = "completed"
            state.event.set()
            return {"turn": {"id": "turn_1"}}
        raise AssertionError(f"Unexpected RPC: {method}")

    monkeypatch.setattr(transport, "_rpc", fake_rpc)

    def fake_wait(turn_id: str, timeout_sec: int):
        assert timeout_sec == 5
        state = transport._get_turn_state(turn_id)
        assert state.event.is_set()
        assert state.stdout_parts == ["early result"]
        assert state.turn_status == "completed"
        assert state.tool_calls == [
            {"tool_name": "emit_spec_content", "arguments": {"content": "# Spec"}}
        ]
        return (
            "".join(state.stdout_parts),
            list(state.tool_calls),
            state.turn_status,
            state.final_plan_item,
            list(state.runtime_request_ids),
        )

    monkeypatch.setattr(transport, "_wait_for_turn_result", fake_wait)

    response = transport.send_prompt_streaming("hello", timeout_sec=5)

    assert response == {
        "stdout": "early result",
        "thread_id": "thread_1",
        "turn_id": "turn_1",
        "tool_calls": [
            {"tool_name": "emit_spec_content", "arguments": {"content": "# Spec"}}
        ],
        "turn_status": "completed",
        "final_plan_item": None,
        "runtime_request_ids": [],
    }


def test_reasoning_and_output_delta_events_surface_through_on_raw_event() -> None:
    transport = StdioTransport()
    seen: list[dict[str, Any]] = []
    state = transport._get_turn_state("turn_1")
    state.on_raw_event = seen.append
    state.callbacks_attached = True

    transport._handle_notification(
        "item/reasoning/summaryDelta",
        {"turnId": "turn_1", "threadId": "thread_1", "itemId": "reason-1", "delta": "think"},
    )
    transport._handle_notification(
        "item/commandExecution/outputDelta",
        {"turnId": "turn_1", "threadId": "thread_1", "itemId": "cmd-1", "delta": "stdout"},
    )
    transport._handle_notification(
        "item/commandExecution/terminalInteraction",
        {"turnId": "turn_1", "threadId": "thread_1", "itemId": "cmd-1", "stdin": "y\n"},
    )
    transport._handle_notification(
        "item/fileChange/outputDelta",
        {"turnId": "turn_1", "threadId": "thread_1", "itemId": "file-1", "delta": "patch"},
    )

    assert [event["method"] for event in seen] == [
        "item/reasoning/summaryDelta",
        "item/commandExecution/outputDelta",
        "item/commandExecution/terminalInteraction",
        "item/fileChange/outputDelta",
    ]
    assert [event["item_id"] for event in seen] == ["reason-1", "cmd-1", "cmd-1", "file-1"]


def test_notification_routing_falls_back_to_unique_thread_state_without_turn_id() -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, object]] = []
    items_seen: list[tuple[str, dict[str, object]]] = []
    deltas: list[str] = []

    state = transport._get_turn_state("turn_1")
    state.thread_id = "thread_1"
    state.on_raw_event = raw_seen.append
    state.on_item_event = lambda phase, item: items_seen.append((phase, item))
    state.on_delta = deltas.append
    state.callbacks_attached = True

    command_item = {
        "type": "commandExecution",
        "id": "cmd-1",
        "command": "npm test",
    }

    transport._handle_notification(
        "item/started",
        {"threadId": "thread_1", "item": command_item},
    )
    transport._handle_notification(
        "item/agentMessage/delta",
        {"threadId": "thread_1", "itemId": "msg-1", "delta": "hello"},
    )
    transport._handle_notification(
        "item/commandExecution/outputDelta",
        {"threadId": "thread_1", "itemId": "cmd-1", "delta": "stdout"},
    )
    transport._handle_notification(
        "item/commandExecution/terminalInteraction",
        {"threadId": "thread_1", "itemId": "cmd-1", "stdin": "y\n"},
    )
    transport._handle_notification(
        "item/completed",
        {"threadId": "thread_1", "item": {**command_item, "status": "completed"}},
    )

    assert deltas == ["hello"]
    assert items_seen == [
        ("started", command_item),
        ("completed", {**command_item, "status": "completed"}),
    ]
    assert [event["method"] for event in raw_seen] == [
        "item/started",
        "item/agentMessage/delta",
        "item/commandExecution/outputDelta",
        "item/commandExecution/terminalInteraction",
        "item/completed",
    ]
    assert all(event["turn_id"] == "turn_1" for event in raw_seen)


def test_turn_completed_accepts_top_level_turn_id_and_marks_event_set() -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, object]] = []

    state = transport._get_turn_state("turn_1")
    state.thread_id = "thread_1"
    state.on_raw_event = raw_seen.append
    state.callbacks_attached = True

    transport._handle_notification(
        "turn/completed",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "status": "completed",
        },
    )

    assert state.event.is_set()
    assert state.turn_status == "completed"
    assert raw_seen == [
        {
            "method": "turn/completed",
            "received_at": raw_seen[0]["received_at"],
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "item_id": None,
            "request_id": None,
            "call_id": None,
            "params": {
                "threadId": "thread_1",
                "turnId": "turn_1",
                "status": "completed",
            },
        }
    ]


def test_turn_completed_routes_by_unique_thread_id_without_turn_id() -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, object]] = []

    state = transport._get_turn_state("turn_1")
    state.thread_id = "thread_1"
    state.on_raw_event = raw_seen.append
    state.callbacks_attached = True

    transport._handle_notification(
        "turn/completed",
        {
            "threadId": "thread_1",
            "turn": {"status": "completed"},
        },
    )

    assert state.event.is_set()
    assert state.turn_status == "completed"
    assert raw_seen[0]["turn_id"] == "turn_1"
    assert raw_seen[0]["thread_id"] == "thread_1"


def test_reasoning_alias_methods_are_normalized_before_dispatch() -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, object]] = []

    state = transport._get_turn_state("turn_1")
    state.thread_id = "thread_1"
    state.on_raw_event = raw_seen.append
    state.callbacks_attached = True

    transport._handle_notification(
        "item/reasoning/summaryTextDelta",
        {"threadId": "thread_1", "itemId": "reason-1", "delta": "think"},
    )
    transport._handle_notification(
        "item/reasoning/textDelta",
        {"threadId": "thread_1", "itemId": "reason-1", "delta": "details"},
    )

    assert [event["method"] for event in raw_seen] == [
        "item/reasoning/summaryDelta",
        "item/reasoning/detailDelta",
    ]
    assert all(event["turn_id"] == "turn_1" for event in raw_seen)


def test_ambiguous_thread_id_notification_is_dropped_with_debug_log(caplog) -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, object]] = []

    first = transport._get_turn_state("turn_1")
    first.thread_id = "thread_1"
    first.on_raw_event = raw_seen.append
    first.callbacks_attached = True

    second = transport._get_turn_state("turn_2")
    second.thread_id = "thread_1"
    second.on_raw_event = raw_seen.append
    second.callbacks_attached = True

    with caplog.at_level(logging.DEBUG):
        transport._handle_notification(
            "item/started",
            {"threadId": "thread_1", "item": {"type": "agentMessage", "id": "msg-1"}},
        )

    assert raw_seen == []
    assert "ambiguous_or_missing_thread_match" in caplog.text


def test_request_user_input_and_resolved_emit_raw_and_legacy_payloads(monkeypatch) -> None:
    transport = StdioTransport()
    requested_seen: list[dict[str, Any]] = []
    resolved_seen: list[dict[str, Any]] = []
    raw_seen: list[dict[str, Any]] = []
    state = transport._get_turn_state("turn_1")
    state.on_request_user_input = requested_seen.append
    state.on_request_resolved = resolved_seen.append
    state.on_raw_event = raw_seen.append
    state.callbacks_attached = True

    monkeypatch.setattr(transport, "_send_response", lambda request_id, result: None)

    transport._handle_server_request(
        55,
        "item/tool/requestUserInput",
        {
            "threadId": "thread_1",
            "turnId": "turn_1",
            "itemId": "input-1",
            "questions": [{"id": "q1", "prompt": "Choose"}],
        },
    )

    record = transport.resolve_runtime_request_user_input("55", answers={"q1": "a"})
    assert record is not None
    assert record.status == "answer_submitted"
    assert record.submitted_at is not None

    transport._handle_notification(
        "serverRequest/resolved",
        {"threadId": "thread_1", "requestId": 55},
    )

    assert requested_seen == [
        {
            "request_id": "55",
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "item_id": "input-1",
            "questions": [{"id": "q1", "prompt": "Choose"}],
            "created_at": requested_seen[0]["created_at"],
            "status": "pending",
        }
    ]
    assert resolved_seen == [
        {
            "request_id": "55",
            "item_id": "input-1",
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "status": "answered",
            "answers": {"q1": "a"},
            "submitted_at": record.submitted_at,
            "resolved_at": resolved_seen[0]["resolved_at"],
        }
    ]
    assert [event["method"] for event in raw_seen] == [
        "item/tool/requestUserInput",
        "serverRequest/resolved",
    ]
    assert raw_seen[0]["request_id"] == "55"
    assert raw_seen[0]["item_id"] == "input-1"
    assert raw_seen[1]["request_id"] == "55"
    assert raw_seen[1]["item_id"] == "input-1"


def test_request_and_resolved_events_buffer_without_preexisting_turn_state(monkeypatch) -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []

    monkeypatch.setattr(transport, "is_alive", lambda: True)
    monkeypatch.setattr(transport, "_initialize_session", lambda timeout_sec: None)
    monkeypatch.setattr(transport, "_send_response", lambda request_id, result: None)

    def fake_rpc(method: str, params: dict[str, object], timeout: int = 30) -> dict[str, object]:
        if method != "turn/start":
            raise AssertionError(f"Unexpected RPC: {method}")

        turn_id = "turn_early"
        transport._handle_server_request(
            78,
            "item/tool/requestUserInput",
            {
                "threadId": "thread_1",
                "turnId": turn_id,
                "itemId": "input-1",
                "questions": [{"id": "q1", "prompt": "Choose"}],
            },
        )
        submitted = transport.resolve_runtime_request_user_input("78", answers={"q1": "ok"})
        assert submitted is not None
        transport._handle_notification("serverRequest/resolved", {"threadId": "thread_1", "requestId": 78})
        transport._handle_notification(
            "turn/completed",
            {"threadId": "thread_1", "turn": {"id": turn_id, "status": "completed"}},
        )
        return {"turn": {"id": turn_id}}

    monkeypatch.setattr(transport, "_rpc", fake_rpc)
    monkeypatch.setattr(
        transport,
        "_wait_for_turn_result",
        lambda turn_id, timeout_sec: ("", [], "completed", None, list(transport._get_turn_state(turn_id).runtime_request_ids)),
    )

    transport.run_turn_streaming(
        "hello",
        thread_id="thread_1",
        on_raw_event=raw_seen.append,
        on_request_user_input=requests.append,
        on_request_resolved=resolutions.append,
    )

    assert [event["method"] for event in raw_seen] == [
        "item/tool/requestUserInput",
        "serverRequest/resolved",
        "turn/completed",
    ]
    assert requests[0]["request_id"] == "78"
    assert requests[0]["item_id"] == "input-1"
    assert resolutions[0]["request_id"] == "78"
    assert resolutions[0]["item_id"] == "input-1"


def test_tool_call_raw_event_preserves_original_payload() -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, Any]] = []
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    state = transport._get_turn_state("turn_1")
    state.on_raw_event = raw_seen.append
    state.on_tool_call = lambda tool_name, arguments: tool_calls.append((tool_name, arguments))
    state.callbacks_attached = True

    payload = {
        "turnId": "turn_1",
        "threadId": "thread_1",
        "callId": "call-1",
        "toolName": "read_file",
        "arguments": {"path": "/tmp.txt"},
        "extraField": "keep-me",
    }
    transport._handle_server_request(77, "item/tool/call", payload)

    assert tool_calls == [("read_file", {"path": "/tmp.txt"})]
    assert raw_seen[0]["method"] == "item/tool/call"
    assert raw_seen[0]["call_id"] == "call-1"
    assert raw_seen[0]["params"]["toolName"] == "read_file"
    assert raw_seen[0]["params"]["extraField"] == "keep-me"
    assert raw_seen[0]["params"]["tool_name"] == "read_file"
    assert raw_seen[0]["params"]["call_id"] == "call-1"
    assert raw_seen[0]["params"]["raw_request"] == payload


def test_raw_event_replay_preserves_buffer_order_when_live_event_arrives_during_replay() -> None:
    transport = StdioTransport()
    state = transport._get_turn_state("turn_1")
    state.callbacks_attached = True
    state.raw_events = [
        {
            "method": "event-1",
            "received_at": "2026-03-28T10:00:00Z",
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "item_id": None,
            "request_id": None,
            "call_id": None,
            "params": {},
        },
        {
            "method": "event-2",
            "received_at": "2026-03-28T10:00:01Z",
            "thread_id": "thread_1",
            "turn_id": "turn_1",
            "item_id": None,
            "request_id": None,
            "call_id": None,
            "params": {},
        },
    ]
    seen: list[str] = []
    injected = False
    original_dispatch = transport._dispatch_raw_event

    def fake_dispatch(state_arg: Any, raw_event: dict[str, Any]) -> None:
        nonlocal injected
        seen.append(str(raw_event["method"]))
        if raw_event["method"] == "event-1" and not injected:
            injected = True
            transport._record_and_dispatch_raw_event(
                state_arg,
                {
                    "method": "event-3",
                    "received_at": "2026-03-28T10:00:02Z",
                    "thread_id": "thread_1",
                    "turn_id": "turn_1",
                    "item_id": None,
                    "request_id": None,
                    "call_id": None,
                    "params": {},
                },
            )
        original_dispatch(state_arg, raw_event)

    transport._dispatch_raw_event = fake_dispatch  # type: ignore[method-assign]
    transport._replay_buffered_raw_events(state)

    assert seen == ["event-1", "event-2", "event-3"]


def test_run_turn_streaming_replays_early_buffered_raw_events(monkeypatch) -> None:
    transport = StdioTransport()
    raw_seen: list[dict[str, Any]] = []
    deltas: list[str] = []
    statuses: list[dict[str, Any]] = []
    item_events: list[tuple[str, dict[str, Any]]] = []
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    requests: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []

    monkeypatch.setattr(transport, "is_alive", lambda: True)
    monkeypatch.setattr(transport, "_initialize_session", lambda timeout_sec: None)
    monkeypatch.setattr(transport, "_send_response", lambda request_id, result: None)

    def fake_rpc(method: str, params: dict[str, object], timeout: int = 30) -> dict[str, object]:
        if method != "turn/start":
            raise AssertionError(f"Unexpected RPC: {method}")

        turn_id = "turn_1"
        transport._handle_notification(
            "item/agentMessage/delta",
            {"turnId": turn_id, "threadId": "thread_1", "itemId": "msg-1", "delta": "hello"},
        )
        transport._handle_notification(
            "item/started",
            {"turnId": turn_id, "item": {"type": "commandExecution", "id": "cmd-1", "status": "inProgress"}},
        )
        transport._handle_server_request(
            77,
            "item/tool/call",
            {"turnId": turn_id, "threadId": "thread_1", "callId": "call-1", "toolName": "read_file", "arguments": {"path": "/tmp.txt"}},
        )
        transport._handle_server_request(
            78,
            "item/tool/requestUserInput",
            {"threadId": "thread_1", "turnId": turn_id, "itemId": "input-1", "questions": [{"id": "q1"}]},
        )
        submitted = transport.resolve_runtime_request_user_input("78", answers={"q1": "ok"})
        assert submitted is not None
        transport._handle_notification("thread/status/changed", {"threadId": "thread_1", "status": {"type": "running"}})
        transport._handle_notification("serverRequest/resolved", {"threadId": "thread_1", "requestId": 78})
        transport._handle_notification(
            "turn/completed",
            {"threadId": "thread_1", "turn": {"id": turn_id, "status": "completed"}},
        )
        return {"turn": {"id": turn_id}}

    monkeypatch.setattr(transport, "_rpc", fake_rpc)

    def fake_wait(turn_id: str, timeout_sec: int):
        state = transport._get_turn_state(turn_id)
        return (
            "".join(state.stdout_parts),
            list(state.tool_calls),
            state.turn_status,
            state.final_plan_item,
            list(state.runtime_request_ids),
        )

    monkeypatch.setattr(transport, "_wait_for_turn_result", fake_wait)

    result = transport.run_turn_streaming(
        "hello",
        thread_id="thread_1",
        on_raw_event=raw_seen.append,
        on_delta=deltas.append,
        on_thread_status=statuses.append,
        on_item_event=lambda phase, item: item_events.append((phase, item)),
        on_tool_call=lambda tool_name, arguments: tool_calls.append((tool_name, arguments)),
        on_request_user_input=requests.append,
        on_request_resolved=resolutions.append,
    )

    assert result["stdout"] == "hello"
    assert result["turn_status"] == "completed"
    assert deltas == ["hello"]
    assert statuses == [{"thread_id": "thread_1", "status": {"type": "running"}}]
    assert item_events == [
        ("started", {"type": "commandExecution", "id": "cmd-1", "status": "inProgress"})
    ]
    assert tool_calls == [("read_file", {"path": "/tmp.txt"})]
    assert requests[0]["request_id"] == "78"
    assert requests[0]["item_id"] == "input-1"
    assert resolutions[0]["request_id"] == "78"
    assert resolutions[0]["item_id"] == "input-1"
    assert [event["method"] for event in raw_seen] == [
        "item/agentMessage/delta",
        "item/started",
        "item/tool/call",
        "item/tool/requestUserInput",
        "thread/status/changed",
        "serverRequest/resolved",
        "turn/completed",
    ]
    assert raw_seen[2]["params"]["toolName"] == "read_file"
    assert raw_seen[2]["params"]["tool_name"] == "read_file"
    assert raw_seen[2]["params"]["raw_request"]["callId"] == "call-1"
