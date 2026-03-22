from __future__ import annotations

import asyncio
import json
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
