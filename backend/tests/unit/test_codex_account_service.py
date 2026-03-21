from __future__ import annotations

import base64
import json
from pathlib import Path

from backend.ai.codex_client import CodexTransportError
from backend.services.codex_account_service import (
    CodexAccountService,
    normalize_rate_limits_payload,
)
from backend.streaming.sse_broker import GlobalEventBroker


def _encode_segment(payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _write_auth_file(codex_home: Path, *, email: str, plan_type: str) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    token_payload = {
        "email": email,
        "https://api.openai.com/auth": {
            "chatgpt_plan_type": plan_type,
        },
    }
    id_token = f"{_encode_segment({'alg': 'none'})}.{_encode_segment(token_payload)}."
    auth_payload = {
        "tokens": {
            "id_token": id_token,
        }
    }
    (codex_home / "auth.json").write_text(
        json.dumps(auth_payload),
        encoding="utf-8",
    )


class FailingAccountClient:
    def add_account_updated_listener(self, callback) -> None:
        self.account_listener = callback

    def add_rate_limits_updated_listener(self, callback) -> None:
        self.rate_limit_listener = callback

    def read_account(self, *, timeout_sec: int = 30) -> dict:
        del timeout_sec
        raise CodexTransportError("not available", "not_found")

    def read_rate_limits(self, *, timeout_sec: int = 30) -> dict:
        del timeout_sec
        return {}


def test_refresh_account_falls_back_to_auth_file(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    _write_auth_file(
        codex_home,
        email="fallback@example.com",
        plan_type="plus",
    )
    service = CodexAccountService(
        codex_client=FailingAccountClient(),
        event_broker=GlobalEventBroker(),
        codex_home=codex_home,
    )

    snapshot = service.refresh_account(publish=False)

    assert snapshot["account"] == {
        "type": "chatgpt",
        "email": "fallback@example.com",
        "plan_type": "plus",
        "requires_openai_auth": None,
    }


def test_normalize_rate_limits_merges_partial_updates() -> None:
    initial = normalize_rate_limits_payload(
        {
            "result": {
                "rate_limits": {
                    "primary": {
                        "used_percent": "25",
                        "window_duration_mins": 60,
                        "resets_at": 12345,
                    },
                    "secondary": {
                        "usedPercent": 70,
                        "windowDurationMins": 10080,
                        "resetsAt": 99999,
                    },
                    "credits": {
                        "has_credits": True,
                        "unlimited": False,
                        "balance": "5",
                    },
                    "plan_type": "plus",
                }
            }
        }
    )

    updated = normalize_rate_limits_payload(
        {
            "rateLimits": {
                "primary": {"resetsAt": 88888},
                "secondary": {},
                "credits": {"balance": "7"},
            }
        },
        previous=initial,
    )

    assert updated == {
        "primary": {
            "used_percent": 25,
            "window_duration_mins": 60,
            "resets_at": 88888,
        },
        "secondary": {
            "used_percent": 70,
            "window_duration_mins": 10080,
            "resets_at": 99999,
        },
        "credits": {
            "has_credits": True,
            "unlimited": False,
            "balance": "7",
        },
        "plan_type": "plus",
    }
