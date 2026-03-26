from __future__ import annotations

from backend.ai.codex_client import (
    CodexAppClient,
    CodexTransportError,
    StdioTransport,
    _TurnState,
)


def test_codex_app_client_run_turn_streaming_forwards_sandbox_profile(monkeypatch) -> None:
    transport = StdioTransport(codex_cmd="codex")
    client = CodexAppClient(transport)
    client._started = True
    monkeypatch.setattr(transport, "is_alive", lambda: True)

    captured: dict[str, object] = {}

    def fake_run_turn_streaming(prompt: str, **kwargs: object) -> dict[str, object]:
        captured["prompt"] = prompt
        captured.update(kwargs)
        return {"stdout": "{}", "thread_id": str(kwargs.get("thread_id") or "")}

    monkeypatch.setattr(transport, "run_turn_streaming", fake_run_turn_streaming)

    schema = {"type": "object"}
    result = client.run_turn_streaming(
        "Review this package.",
        thread_id="review-thread-1",
        cwd="C:/repo",
        sandbox_profile="read_only",
        output_schema=schema,
    )

    assert result["thread_id"] == "review-thread-1"
    assert captured["prompt"] == "Review this package."
    assert captured["sandbox_profile"] == "read_only"
    assert captured["output_schema"] == schema


def test_stdio_transport_run_turn_streaming_uses_non_danger_read_only_policy(monkeypatch) -> None:
    transport = StdioTransport(codex_cmd="codex")
    monkeypatch.setattr(transport, "is_alive", lambda: True)
    monkeypatch.setattr(transport, "_initialize_session", lambda timeout_sec: None)
    monkeypatch.setattr(transport, "_get_turn_state", lambda turn_id: _TurnState())
    monkeypatch.setattr(
        transport,
        "_wait_for_turn_result",
        lambda turn_id, timeout_sec: ("{}", [], None, None, []),
    )

    captured: dict[str, object] = {}

    def fake_rpc(method: str, params: dict[str, object], timeout: int = 30) -> dict[str, object]:
        captured["method"] = method
        captured["params"] = params
        captured["timeout"] = timeout
        return {"turn": {"id": "turn-1"}}

    monkeypatch.setattr(transport, "_rpc", fake_rpc)

    schema = {"type": "object", "required": ["summary"]}
    result = transport.run_turn_streaming(
        "Analyze this review package.",
        thread_id="review-thread-1",
        cwd="C:/repo",
        sandbox_profile="read_only",
        output_schema=schema,
    )

    assert result["thread_id"] == "review-thread-1"
    params = captured["params"]
    assert isinstance(params, dict)
    sandbox_policy = params["sandboxPolicy"]
    assert isinstance(sandbox_policy, dict)
    assert sandbox_policy["type"] == "workspaceWrite"
    assert sandbox_policy["writableRoots"] == []
    assert sandbox_policy["readOnlyAccess"]["readableRoots"] == ["C:/repo"]
    assert params["outputSchema"] == schema


def test_stdio_transport_rejects_unknown_sandbox_profile() -> None:
    transport = StdioTransport(codex_cmd="codex")

    try:
        transport._turn_sandbox_policy("C:/repo", None, sandbox_profile="mystery")
    except CodexTransportError as exc:
        assert exc.error_code == "invalid_sandbox_profile"
    else:
        raise AssertionError("Expected invalid sandbox profile to raise CodexTransportError")
