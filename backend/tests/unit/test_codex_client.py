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
