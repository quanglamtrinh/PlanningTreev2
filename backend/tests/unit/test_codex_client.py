from __future__ import annotations

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


def test_global_account_notifications_do_not_break_turn_scoped_notifications() -> None:
    transport = StdioTransport()
    account_updates: list[dict[str, object]] = []
    rate_limit_updates: list[dict[str, object]] = []
    deltas: list[str] = []

    transport.add_account_updated_listener(account_updates.append)
    transport.add_rate_limits_updated_listener(rate_limit_updates.append)

    state = transport._get_turn_state("turn_1")
    state.on_delta = deltas.append

    transport._handle_notification("account/updated", {"authMode": "chatgpt"})
    transport._handle_notification(
        "account/rateLimits/updated",
        {"rateLimits": {"primary": {"usedPercent": 10}}},
    )
    transport._handle_notification(
        "item/agentMessage/delta",
        {"turnId": "turn_1", "delta": "hello"},
    )

    assert account_updates == [{"authMode": "chatgpt"}]
    assert rate_limit_updates == [{"rateLimits": {"primary": {"usedPercent": 10}}}]
    assert deltas == ["hello"]
