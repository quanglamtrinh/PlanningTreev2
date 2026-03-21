from __future__ import annotations

import base64
import copy
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.streaming.sse_broker import GlobalEventBroker
from backend.storage.file_utils import load_json

logger = logging.getLogger(__name__)


def _has_own(source: dict[str, Any], key: str) -> bool:
    return key in source


def _as_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value == value and value not in (float("inf"), float("-inf")):
            return float(value)
        return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            parsed = float(candidate)
        except ValueError:
            return None
        if parsed == parsed and parsed not in (float("inf"), float("-inf")):
            return parsed
    return None


def _normalize_optional_int(value: float | None, fallback: int | None) -> int | None:
    if value is None:
        return fallback
    return int(round(value))


def _clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _normalize_rate_limit_window(
    source: dict[str, Any],
    previous_window: dict[str, Any] | None,
) -> dict[str, Any] | None:
    direct_used = _as_number(source.get("usedPercent", source.get("used_percent")))
    remaining = _as_number(
        source.get(
            "remainingPercent",
            source.get("remaining_percent", source.get("remaining")),
        )
    )

    used_percent: int | None = None
    if direct_used is not None:
        used_percent = _clamp_percent(direct_used)
    elif remaining is not None:
        used_percent = _clamp_percent(100 - remaining)
    elif previous_window is not None:
        previous_used = previous_window.get("used_percent")
        if isinstance(previous_used, int):
            used_percent = previous_used

    if used_percent is None:
        return None

    previous_duration = previous_window.get("window_duration_mins") if previous_window else None
    previous_reset = previous_window.get("resets_at") if previous_window else None

    return {
        "used_percent": used_percent,
        "window_duration_mins": _normalize_optional_int(
            _as_number(source.get("windowDurationMins", source.get("window_duration_mins"))),
            previous_duration if isinstance(previous_duration, int) else None,
        ),
        "resets_at": _normalize_optional_int(
            _as_number(source.get("resetsAt", source.get("resets_at"))),
            previous_reset if isinstance(previous_reset, int) else None,
        ),
    }


def _normalize_credits_snapshot(
    source: dict[str, Any],
    previous_credits: dict[str, Any] | None,
) -> dict[str, Any]:
    previous_has_credits = (
        previous_credits.get("has_credits") if previous_credits is not None else False
    )
    previous_unlimited = previous_credits.get("unlimited") if previous_credits is not None else False
    previous_balance = previous_credits.get("balance") if previous_credits is not None else None
    has_credits = _as_bool(source.get("hasCredits", source.get("has_credits")))
    unlimited = _as_bool(source.get("unlimited"))

    balance_value: str | None
    if _has_own(source, "balance") and source.get("balance") is None:
        balance_value = None
    elif source.get("balance") is None:
        balance_value = previous_balance if isinstance(previous_balance, str) else None
    else:
        balance_value = _as_string(source.get("balance"))

    return {
        "has_credits": has_credits if has_credits is not None else bool(previous_has_credits),
        "unlimited": unlimited if unlimited is not None else bool(previous_unlimited),
        "balance": balance_value,
    }


def _unwrap_rate_limits_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result, dict):
            if isinstance(result.get("rateLimits"), dict):
                return result["rateLimits"]
            if isinstance(result.get("rate_limits"), dict):
                return result["rate_limits"]
    if isinstance(payload.get("rateLimits"), dict):
        return payload["rateLimits"]
    if isinstance(payload.get("rate_limits"), dict):
        return payload["rate_limits"]
    return payload


def normalize_rate_limits_payload(
    payload: Any,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    raw = _unwrap_rate_limits_payload(payload)
    if not raw:
        return copy.deepcopy(previous) if previous is not None else None

    previous_primary = previous.get("primary") if previous else None
    previous_secondary = previous.get("secondary") if previous else None
    previous_credits = previous.get("credits") if previous else None

    primary = (
        None
        if _has_own(raw, "primary") and raw.get("primary") is None
        else _normalize_rate_limit_window(raw["primary"], previous_primary)
        if _has_own(raw, "primary") and isinstance(raw.get("primary"), dict)
        else copy.deepcopy(previous_primary)
    )
    secondary = (
        None
        if _has_own(raw, "secondary") and raw.get("secondary") is None
        else _normalize_rate_limit_window(raw["secondary"], previous_secondary)
        if _has_own(raw, "secondary") and isinstance(raw.get("secondary"), dict)
        else copy.deepcopy(previous_secondary)
    )
    credits = (
        None
        if _has_own(raw, "credits") and raw.get("credits") is None
        else _normalize_credits_snapshot(raw["credits"], previous_credits)
        if _has_own(raw, "credits") and isinstance(raw.get("credits"), dict)
        else copy.deepcopy(previous_credits)
    )

    has_plan_type_key = _has_own(raw, "planType") or _has_own(raw, "plan_type")
    plan_type = _as_string(raw.get("planType", raw.get("plan_type")))
    previous_plan_type = previous.get("plan_type") if previous else None

    normalized = {
        "primary": primary,
        "secondary": secondary,
        "credits": credits,
        "plan_type": plan_type if plan_type is not None or has_plan_type_key else previous_plan_type,
    }
    return normalized


def _extract_account_map(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result, dict) and isinstance(result.get("account"), dict):
            return result["account"]
    if isinstance(payload.get("account"), dict):
        return payload["account"]
    if any(key in payload for key in ("type", "email", "planType", "plan_type")):
        return payload
    return None


def _extract_requires_openai_auth(payload: Any) -> bool | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result, dict):
            value = result.get("requiresOpenaiAuth", result.get("requires_openai_auth"))
            parsed = _as_bool(value)
            if parsed is not None:
                return parsed
    return _as_bool(payload.get("requiresOpenaiAuth", payload.get("requires_openai_auth")))


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
    except Exception:
        return None
    try:
        candidate = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    return candidate if isinstance(candidate, dict) else None


def resolve_codex_home(override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    env_override = os.environ.get("CODEX_HOME")
    if env_override:
        return Path(env_override).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def read_auth_account(codex_home: Path | None = None) -> dict[str, Any] | None:
    auth_path = resolve_codex_home(codex_home) / "auth.json"
    auth_payload = load_json(auth_path, default=None)
    if not isinstance(auth_payload, dict):
        return None
    tokens = auth_payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    id_token = _as_string(tokens.get("idToken", tokens.get("id_token")))
    if id_token is None:
        return None
    jwt_payload = _decode_jwt_payload(id_token)
    if jwt_payload is None:
        return None

    auth_claims = jwt_payload.get("https://api.openai.com/auth")
    profile_claims = jwt_payload.get("https://api.openai.com/profile")
    auth_claims = auth_claims if isinstance(auth_claims, dict) else {}
    profile_claims = profile_claims if isinstance(profile_claims, dict) else {}

    email = _as_string(jwt_payload.get("email")) or _as_string(profile_claims.get("email"))
    plan_type = _as_string(auth_claims.get("chatgpt_plan_type")) or _as_string(
        jwt_payload.get("chatgpt_plan_type")
    )
    if email is None and plan_type is None:
        return None
    return {
        "email": email,
        "plan_type": plan_type,
    }


def normalize_account_payload(
    payload: Any,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    raw_account = _extract_account_map(payload) or {}
    requires_openai_auth = _extract_requires_openai_auth(payload)
    account_type = _as_string(raw_account.get("type"))
    normalized_type = account_type.lower() if account_type is not None else None
    if normalized_type not in {"chatgpt", "apikey"}:
        normalized_type = "unknown" if normalized_type is not None else None

    allow_fallback = not raw_account or normalized_type in {None, "chatgpt", "unknown"}
    email = _as_string(raw_account.get("email"))
    plan_type = _as_string(raw_account.get("planType", raw_account.get("plan_type")))

    if allow_fallback and fallback is not None:
        email = email or _as_string(fallback.get("email"))
        plan_type = plan_type or _as_string(fallback.get("plan_type"))
        if normalized_type is None:
            normalized_type = "chatgpt"

    if normalized_type is None and (email is not None or plan_type is not None or requires_openai_auth is not None):
        normalized_type = "unknown"

    if normalized_type is None and email is None and plan_type is None and requires_openai_auth is None:
        return None

    return {
        "type": normalized_type or "unknown",
        "email": email,
        "plan_type": plan_type,
        "requires_openai_auth": requires_openai_auth,
    }


class CodexAccountService:
    def __init__(
        self,
        codex_client: CodexAppClient,
        event_broker: GlobalEventBroker,
        *,
        codex_home: Path | None = None,
    ) -> None:
        self._codex_client = codex_client
        self._event_broker = event_broker
        self._codex_home = codex_home
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = {
            "account": None,
            "rate_limits": None,
        }
        self._loaded = False
        self._codex_client.add_account_updated_listener(self._handle_account_updated_notification)
        self._codex_client.add_rate_limits_updated_listener(self._handle_rate_limits_updated_notification)

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            loaded = self._loaded
        if not loaded:
            self.refresh_snapshot(publish=False)
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def refresh_snapshot(self, *, publish: bool = False) -> dict[str, Any]:
        fallback = read_auth_account(self._codex_home)
        with self._lock:
            previous_snapshot = copy.deepcopy(self._snapshot)

        account = previous_snapshot.get("account")
        rate_limits = previous_snapshot.get("rate_limits")

        try:
            account = normalize_account_payload(
                self._codex_client.read_account(timeout_sec=15),
                fallback=fallback,
            )
        except Exception:
            logger.debug("Failed to refresh Codex account info", exc_info=True)
            if account is None and fallback is not None:
                account = normalize_account_payload({}, fallback=fallback)

        try:
            rate_limits = normalize_rate_limits_payload(
                self._codex_client.read_rate_limits(timeout_sec=15),
                previous=rate_limits if isinstance(rate_limits, dict) else None,
            )
        except Exception:
            logger.debug("Failed to refresh Codex rate limits", exc_info=True)

        snapshot = {
            "account": account,
            "rate_limits": rate_limits,
        }

        with self._lock:
            changed = snapshot != self._snapshot or not self._loaded
            self._snapshot = copy.deepcopy(snapshot)
            self._loaded = True

        if publish and changed:
            self._publish_snapshot(snapshot)
        return copy.deepcopy(snapshot)

    def refresh_account(self, *, publish: bool = True) -> dict[str, Any]:
        fallback = read_auth_account(self._codex_home)
        with self._lock:
            snapshot = copy.deepcopy(self._snapshot)

        account = snapshot.get("account")
        try:
            account = normalize_account_payload(
                self._codex_client.read_account(timeout_sec=15),
                fallback=fallback,
            )
        except Exception:
            logger.debug("Failed to refresh Codex account info", exc_info=True)
            if account is None and fallback is not None:
                account = normalize_account_payload({}, fallback=fallback)

        snapshot["account"] = account
        return self._commit_snapshot(snapshot, publish=publish)

    def merge_rate_limits_update(self, payload: dict[str, Any], *, publish: bool = True) -> dict[str, Any]:
        with self._lock:
            snapshot = copy.deepcopy(self._snapshot)
            previous_rate_limits = snapshot.get("rate_limits")

        snapshot["rate_limits"] = normalize_rate_limits_payload(
            payload,
            previous=previous_rate_limits if isinstance(previous_rate_limits, dict) else None,
        )
        return self._commit_snapshot(snapshot, publish=publish)

    def _commit_snapshot(self, snapshot: dict[str, Any], *, publish: bool) -> dict[str, Any]:
        with self._lock:
            changed = snapshot != self._snapshot or not self._loaded
            self._snapshot = copy.deepcopy(snapshot)
            self._loaded = True
        if publish and changed:
            self._publish_snapshot(snapshot)
        return copy.deepcopy(snapshot)

    def _publish_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._event_broker.publish(copy.deepcopy(snapshot))

    def _handle_account_updated_notification(self, payload: dict[str, Any]) -> None:
        del payload
        threading.Thread(
            target=self.refresh_account,
            kwargs={"publish": True},
            daemon=True,
        ).start()

    def _handle_rate_limits_updated_notification(self, payload: dict[str, Any]) -> None:
        try:
            self.merge_rate_limits_update(payload, publish=True)
        except Exception:
            logger.debug("Failed to merge Codex rate limits update", exc_info=True)
