from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.routes import codex as codex_route_module


class FakeCodexAccountClient:
    def read_account(self, *, timeout_sec: int = 30) -> dict:
        del timeout_sec
        return {
            "account": {
                "type": "chatgpt",
                "email": "user@example.com",
                "planType": "plus",
            },
            "requiresOpenaiAuth": True,
        }

    def read_rate_limits(self, *, timeout_sec: int = 30) -> dict:
        del timeout_sec
        return {
            "rateLimits": {
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 11111,
                },
                "secondary": {
                    "used_percent": 60,
                    "window_duration_mins": 10080,
                    "resets_at": 22222,
                },
                "credits": {
                    "hasCredits": True,
                    "unlimited": False,
                    "balance": "8",
                },
                "planType": "plus",
            }
        }


class _StreamingTestRequest:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._is_disconnected = False

    async def is_disconnected(self) -> bool:
        return self._is_disconnected

    def disconnect(self) -> None:
        self._is_disconnected = True


def _reset_codex_snapshot(client: TestClient) -> None:
    client.app.state.codex_account_service._loaded = False
    client.app.state.codex_account_service._snapshot = {
        "account": None,
        "rate_limits": None,
    }


def _today_day_key() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _timestamp_ms_for_day(day_key: str, *, hour: int, minute: int, second: int) -> int:
    local_tz = datetime.now().astimezone().tzinfo
    day = datetime.strptime(day_key, "%Y-%m-%d")
    local_dt = day.replace(
        hour=hour,
        minute=minute,
        second=second,
        microsecond=0,
        tzinfo=local_tz,
    )
    return int(local_dt.timestamp() * 1000)


def _write_usage_session_file(
    codex_home: Path,
    day_key: str,
    lines: list[str],
    *,
    name: str = "usage.jsonl",
) -> Path:
    year, month, day = day_key.split("-")
    day_dir = codex_home / "sessions" / year / month / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _token_count_total_event(
    timestamp_ms: int,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    model_name: str | None = None,
) -> str:
    info: dict[str, Any] = {
        "total_token_usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
        }
    }
    if model_name is not None:
        info["model_name"] = model_name
    return json.dumps(
        {
            "timestamp": timestamp_ms,
            "payload": {
                "type": "token_count",
                "info": info,
            },
        }
    )


async def _read_stream_chunk(response: Any, *, timeout_sec: float = 1.0) -> str:
    return await asyncio.wait_for(anext(response.body_iterator), timeout=timeout_sec)


async def _close_stream(response: Any, request: _StreamingTestRequest) -> None:
    request.disconnect()
    body_iterator = response.body_iterator
    if hasattr(body_iterator, "aclose"):
        await body_iterator.aclose()


def test_get_codex_account_snapshot_returns_normalized_shape(client: TestClient) -> None:
    _reset_codex_snapshot(client)
    client.app.state.codex_account_service._codex_client = FakeCodexAccountClient()

    response = client.get("/v1/codex/account")

    assert response.status_code == 200
    assert response.json() == {
        "account": {
            "type": "chatgpt",
            "email": "user@example.com",
            "plan_type": "plus",
            "requires_openai_auth": True,
        },
        "rate_limits": {
            "primary": {
                "used_percent": 25,
                "window_duration_mins": 300,
                "resets_at": 11111,
            },
            "secondary": {
                "used_percent": 60,
                "window_duration_mins": 10080,
                "resets_at": 22222,
            },
            "credits": {
                "has_credits": True,
                "unlimited": False,
                "balance": "8",
            },
            "plan_type": "plus",
        },
    }


def test_get_local_usage_snapshot_returns_expected_shape(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    day_key = _today_day_key()
    timestamp_ms = _timestamp_ms_for_day(day_key, hour=11, minute=0, second=0)
    _write_usage_session_file(
        codex_home,
        day_key,
        [
            _token_count_total_event(
                timestamp_ms,
                input_tokens=10,
                cached_input_tokens=2,
                output_tokens=5,
                model_name="gpt-5",
            )
        ],
    )

    response = client.get("/v1/codex/usage/local")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"updated_at", "days", "totals", "top_models"}
    assert len(payload["days"]) == 30
    assert set(payload["days"][-1].keys()) == {
        "day",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "agent_time_ms",
        "agent_runs",
    }
    assert set(payload["totals"].keys()) == {
        "last7_days_tokens",
        "last30_days_tokens",
        "average_daily_tokens",
        "cache_hit_rate_percent",
        "peak_day",
        "peak_day_tokens",
    }
    assert payload["top_models"]
    assert set(payload["top_models"][0].keys()) == {"model", "tokens", "share_percent"}


def test_get_local_usage_snapshot_honors_valid_days_query(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))

    response = client.get("/v1/codex/usage/local?days=7")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["days"]) == 7


@pytest.mark.parametrize(
    ("raw_days", "expected_days"),
    [
        ("0", 1),
        ("-1", 1),
        ("999", 90),
        ("abc", 30),
    ],
)
def test_get_local_usage_snapshot_days_boundaries_and_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw_days: str,
    expected_days: int,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))

    response = client.get(f"/v1/codex/usage/local?days={raw_days}")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["days"]) == expected_days


def test_get_local_usage_snapshot_degraded_input_still_returns_valid_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    day_key = _today_day_key()
    year, month, day = day_key.split("-")
    day_dir = codex_home / "sessions" / year / month / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "broken.jsonl").mkdir()
    (day_dir / "malformed.jsonl").write_text("{not-json\n", encoding="utf-8")

    response = client.get("/v1/codex/usage/local?days=1")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"updated_at", "days", "totals", "top_models"}
    assert len(payload["days"]) == 1
    assert payload["days"][0]["total_tokens"] == 0


@pytest.mark.anyio
async def test_codex_events_emits_snapshot_updated(client: TestClient) -> None:
    snapshot = {
        "account": {
            "type": "chatgpt",
            "email": "live@example.com",
            "plan_type": "plus",
            "requires_openai_auth": True,
        },
        "rate_limits": None,
    }
    request = _StreamingTestRequest(client.app)
    response = await codex_route_module.codex_events(request)

    try:
        assert response.media_type == "text/event-stream"
        assert await _read_stream_chunk(response) == ": connected\n\n"
        client.app.state.codex_event_broker.publish(snapshot)
        chunk = await _read_stream_chunk(response)
    finally:
        await _close_stream(response, request)

    assert chunk == f"event: snapshot_updated\ndata: {json.dumps(snapshot, ensure_ascii=True)}\n\n"
    assert not client.app.state.codex_event_broker._subscribers


@pytest.mark.anyio
async def test_codex_events_emits_heartbeat(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(codex_route_module, "SSE_HEARTBEAT_INTERVAL_SEC", 0.01)
    request = _StreamingTestRequest(client.app)
    response = await codex_route_module.codex_events(request)

    try:
        assert await _read_stream_chunk(response) == ": connected\n\n"
        heartbeat_chunk = await _read_stream_chunk(response)
    finally:
        await _close_stream(response, request)

    assert heartbeat_chunk == ": heartbeat\n\n"
    assert not client.app.state.codex_event_broker._subscribers
