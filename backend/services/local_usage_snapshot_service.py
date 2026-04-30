from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DAYS = 30
MIN_DAYS = 1
MAX_DAYS = 90
MAX_ACTIVITY_GAP_MS = 120_000
MAX_LINE_BYTES = 512_000
DEFAULT_CACHE_TTL_SEC = 30.0

logger = logging.getLogger(__name__)


def _resolve_codex_home(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    raw = os.environ.get("CODEX_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


@dataclass
class DailyTotals:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    agent_time_ms: int = 0
    agent_runs: int = 0


@dataclass
class UsageTotals:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ScanDiagnostics:
    files_visited: int = 0
    files_opened: int = 0
    files_skipped_unreadable: int = 0
    lines_total: int = 0
    lines_invalid_json: int = 0
    lines_oversized: int = 0
    token_events_applied: int = 0
    scan_duration_ms: int = 0
    cache_hit: bool = False

    def with_cache_hit(self, cache_hit: bool) -> ScanDiagnostics:
        return replace(self, cache_hit=cache_hit)


@dataclass
class SnapshotCacheEntry:
    snapshot: dict[str, Any]
    computed_at_monotonic: float
    diagnostics: ScanDiagnostics


class LocalUsageSnapshotService:
    def __init__(self, codex_home: Path | None = None) -> None:
        self._codex_home = codex_home
        self._cache_ttl_sec = DEFAULT_CACHE_TTL_SEC
        self._cache_lock = threading.Lock()
        self._cache: dict[tuple[int, str], SnapshotCacheEntry] = {}
        self._inflight: dict[tuple[int, str], threading.Event] = {}

    def read_snapshot(self, days: Any = None) -> dict[str, Any]:
        normalized_days = _normalize_days(days)
        sessions_root = self._resolve_sessions_root()
        cache_key = (normalized_days, str(sessions_root))

        while True:
            now = time.monotonic()
            cached_entry = self._get_cached_entry(cache_key, now=now)
            if cached_entry is not None:
                diagnostics = cached_entry.diagnostics.with_cache_hit(True)
                self._log_scan_summary(
                    level="debug",
                    normalized_days=normalized_days,
                    sessions_root=sessions_root,
                    diagnostics=diagnostics,
                )
                return copy.deepcopy(cached_entry.snapshot)

            is_owner, waiter = self._begin_single_flight(cache_key)
            if is_owner:
                break
            waiter.wait()

        try:
            snapshot, diagnostics = self._compute_snapshot(
                normalized_days=normalized_days,
                sessions_root=sessions_root,
            )
            with self._cache_lock:
                self._cache[cache_key] = SnapshotCacheEntry(
                    snapshot=copy.deepcopy(snapshot),
                    computed_at_monotonic=time.monotonic(),
                    diagnostics=diagnostics,
                )
                waiter = self._inflight.pop(cache_key, None)
            if waiter is not None:
                waiter.set()
            self._log_scan_summary(
                level="info",
                normalized_days=normalized_days,
                sessions_root=sessions_root,
                diagnostics=diagnostics,
            )
            return copy.deepcopy(snapshot)
        except Exception:
            with self._cache_lock:
                waiter = self._inflight.pop(cache_key, None)
            if waiter is not None:
                waiter.set()
            raise

    def _resolve_sessions_root(self) -> Path:
        return _resolve_codex_home(self._codex_home) / "sessions"

    def _get_cached_entry(
        self,
        cache_key: tuple[int, str],
        *,
        now: float,
    ) -> SnapshotCacheEntry | None:
        with self._cache_lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            if now - entry.computed_at_monotonic > self._cache_ttl_sec:
                self._cache.pop(cache_key, None)
                return None
            return entry

    def _begin_single_flight(self, cache_key: tuple[int, str]) -> tuple[bool, threading.Event]:
        with self._cache_lock:
            waiter = self._inflight.get(cache_key)
            if waiter is None:
                waiter = threading.Event()
                self._inflight[cache_key] = waiter
                return True, waiter
            return False, waiter

    def _compute_snapshot(
        self,
        *,
        normalized_days: int,
        sessions_root: Path,
    ) -> tuple[dict[str, Any], ScanDiagnostics]:
        scan_started = time.monotonic()
        day_keys = _make_day_keys(normalized_days)
        daily: dict[str, DailyTotals] = {day_key: DailyTotals() for day_key in day_keys}
        model_totals: dict[str, int] = {}
        diagnostics = ScanDiagnostics()

        if sessions_root.exists():
            for day_key in day_keys:
                day_dir = _day_dir_for_key(sessions_root, day_key)
                if not day_dir.exists():
                    continue
                try:
                    entries = list(day_dir.iterdir())
                except OSError:
                    continue

                for entry in entries:
                    if entry.suffix != ".jsonl":
                        continue
                    diagnostics.files_visited += 1
                    _scan_file(
                        entry,
                        daily=daily,
                        model_totals=model_totals,
                        diagnostics=diagnostics,
                    )

        diagnostics.scan_duration_ms = max(
            0,
            int(_round_half_away_from_zero((time.monotonic() - scan_started) * 1000)),
        )

        updated_at = int(time.time() * 1000)
        snapshot = _build_snapshot(
            updated_at=updated_at,
            day_keys=day_keys,
            daily=daily,
            model_totals=model_totals,
        )
        return snapshot, diagnostics

    def _log_scan_summary(
        self,
        *,
        level: str,
        normalized_days: int,
        sessions_root: Path,
        diagnostics: ScanDiagnostics,
    ) -> None:
        log_fn = logger.debug if level == "debug" else logger.info
        log_fn(
            (
                "Local usage snapshot read "
                "cache_hit=%s days=%s sessions_root=%s files_visited=%s files_opened=%s "
                "files_skipped_unreadable=%s lines_total=%s lines_invalid_json=%s "
                "lines_oversized=%s token_events_applied=%s scan_duration_ms=%s"
            ),
            diagnostics.cache_hit,
            normalized_days,
            str(sessions_root),
            diagnostics.files_visited,
            diagnostics.files_opened,
            diagnostics.files_skipped_unreadable,
            diagnostics.lines_total,
            diagnostics.lines_invalid_json,
            diagnostics.lines_oversized,
            diagnostics.token_events_applied,
            diagnostics.scan_duration_ms,
        )


def _normalize_days(days: Any | None) -> int:
    if days is None:
        return DEFAULT_DAYS
    parsed = _coerce_int(days)
    if parsed is None:
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, parsed))


def _make_day_keys(days: int) -> list[str]:
    today = datetime.now().astimezone().date()
    return [
        (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days - 1, -1, -1)
    ]


def _day_dir_for_key(root: Path, day_key: str) -> Path:
    year, month, day = (day_key.split("-") + ["1970", "01", "01"])[:3]
    return root / year / month / day


def _scan_file(
    path: Path,
    *,
    daily: dict[str, DailyTotals],
    model_totals: dict[str, int],
    diagnostics: ScanDiagnostics,
) -> None:
    try:
        handle = path.open("rb")
    except OSError:
        diagnostics.files_skipped_unreadable += 1
        return
    diagnostics.files_opened += 1

    previous_totals: UsageTotals | None = None
    current_model: str | None = None
    last_activity_ms: int | None = None
    seen_runs: set[int] = set()

    with handle:
        for raw_line in handle:
            diagnostics.lines_total += 1
            if len(raw_line) > MAX_LINE_BYTES:
                diagnostics.lines_oversized += 1
                continue
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                diagnostics.lines_invalid_json += 1
                continue

            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.lines_invalid_json += 1
                continue
            if not isinstance(value, dict):
                continue

            entry_type = _as_str(value.get("type")) or ""

            if entry_type == "turn_context":
                model = _extract_model_from_turn_context(value)
                if model is not None:
                    current_model = model
                continue

            if entry_type == "session_meta":
                continue

            if entry_type in {"event_msg", ""}:
                payload = value.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_type = _as_str(payload.get("type"))

                if payload_type == "agent_message":
                    timestamp_ms = _read_timestamp_ms(value)
                    if timestamp_ms is not None:
                        _increment_agent_runs(daily, seen_runs, timestamp_ms)
                        last_activity_ms = _track_activity(
                            daily,
                            last_activity_ms=last_activity_ms,
                            timestamp_ms=timestamp_ms,
                        )
                    continue

                if payload_type == "agent_reasoning":
                    timestamp_ms = _read_timestamp_ms(value)
                    if timestamp_ms is not None:
                        last_activity_ms = _track_activity(
                            daily,
                            last_activity_ms=last_activity_ms,
                            timestamp_ms=timestamp_ms,
                        )
                    continue

                if payload_type != "token_count":
                    continue

                info = payload.get("info")
                if not isinstance(info, dict):
                    continue

                usage_map = _find_usage_map(info, ["total_token_usage", "totalTokenUsage"])
                used_total = usage_map is not None
                if usage_map is None:
                    usage_map = _find_usage_map(info, ["last_token_usage", "lastTokenUsage"])
                if usage_map is None:
                    continue

                input_tokens = _read_int(usage_map, ["input_tokens", "inputTokens"])
                cached_input_tokens = _read_int(
                    usage_map,
                    [
                        "cached_input_tokens",
                        "cache_read_input_tokens",
                        "cachedInputTokens",
                        "cacheReadInputTokens",
                    ],
                )
                output_tokens = _read_int(usage_map, ["output_tokens", "outputTokens"])
                delta = UsageTotals(
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_input_tokens,
                    output_tokens=output_tokens,
                )

                if used_total:
                    previous = previous_totals or UsageTotals()
                    delta = UsageTotals(
                        input_tokens=max(0, input_tokens - previous.input_tokens),
                        cached_input_tokens=max(
                            0,
                            cached_input_tokens - previous.cached_input_tokens,
                        ),
                        output_tokens=max(0, output_tokens - previous.output_tokens),
                    )
                    previous_totals = UsageTotals(
                        input_tokens=input_tokens,
                        cached_input_tokens=cached_input_tokens,
                        output_tokens=output_tokens,
                    )
                else:
                    previous = previous_totals or UsageTotals()
                    previous_totals = UsageTotals(
                        input_tokens=previous.input_tokens + delta.input_tokens,
                        cached_input_tokens=(
                            previous.cached_input_tokens + delta.cached_input_tokens
                        ),
                        output_tokens=previous.output_tokens + delta.output_tokens,
                    )

                if (
                    delta.input_tokens == 0
                    and delta.cached_input_tokens == 0
                    and delta.output_tokens == 0
                ):
                    continue

                timestamp_ms = _read_timestamp_ms(value)
                if timestamp_ms is not None:
                    day_key = _day_key_for_timestamp_ms(timestamp_ms)
                    if day_key in daily:
                        entry = daily[day_key]
                        entry.input_tokens += delta.input_tokens
                        entry.cached_input_tokens += min(
                            delta.cached_input_tokens,
                            delta.input_tokens,
                        )
                        entry.output_tokens += delta.output_tokens

                        model = (
                            current_model
                            or _extract_model_from_token_count(value)
                            or "unknown"
                        )
                        model_totals[model] = (
                            model_totals.get(model, 0)
                            + delta.input_tokens
                            + delta.output_tokens
                        )
                        diagnostics.token_events_applied += 1
                    last_activity_ms = _track_activity(
                        daily,
                        last_activity_ms=last_activity_ms,
                        timestamp_ms=timestamp_ms,
                    )
                continue

            if entry_type == "response_item":
                payload = value.get("payload")
                payload_type = _as_str(payload.get("type")) if isinstance(payload, dict) else None
                role = _as_str(payload.get("role")) if isinstance(payload, dict) else None
                timestamp_ms = _read_timestamp_ms(value)
                if timestamp_ms is None:
                    continue

                if role == "assistant":
                    _increment_agent_runs(daily, seen_runs, timestamp_ms)
                    last_activity_ms = _track_activity(
                        daily,
                        last_activity_ms=last_activity_ms,
                        timestamp_ms=timestamp_ms,
                    )
                elif payload_type != "message":
                    last_activity_ms = _track_activity(
                        daily,
                        last_activity_ms=last_activity_ms,
                        timestamp_ms=timestamp_ms,
                    )


def _build_snapshot(
    *,
    updated_at: int,
    day_keys: list[str],
    daily: dict[str, DailyTotals],
    model_totals: dict[str, int],
) -> dict[str, Any]:
    day_rows: list[dict[str, Any]] = []
    total_window_tokens = 0

    for day_key in day_keys:
        totals = daily.get(day_key, DailyTotals())
        total_tokens = totals.input_tokens + totals.output_tokens
        total_window_tokens += total_tokens
        day_rows.append(
            {
                "day": day_key,
                "input_tokens": totals.input_tokens,
                "cached_input_tokens": totals.cached_input_tokens,
                "output_tokens": totals.output_tokens,
                "total_tokens": total_tokens,
                "agent_time_ms": totals.agent_time_ms,
                "agent_runs": totals.agent_runs,
            }
        )

    last7_days = day_rows[-7:]
    last30_days = day_rows[-30:]

    last7_days_tokens = sum(day["total_tokens"] for day in last7_days)
    last30_days_tokens = sum(day["total_tokens"] for day in last30_days)
    last7_input_tokens = sum(day["input_tokens"] for day in last7_days)
    last7_cached_input_tokens = sum(day["cached_input_tokens"] for day in last7_days)

    if last7_days:
        average_daily_tokens = int(
            _round_half_away_from_zero(last7_days_tokens / len(last7_days))
        )
    else:
        average_daily_tokens = 0

    if last7_input_tokens > 0:
        cache_hit_rate_percent = _round_half_away_from_zero(
            (last7_cached_input_tokens / last7_input_tokens) * 100.0,
            digits=1,
        )
    else:
        cache_hit_rate_percent = 0.0

    peak_day = None
    peak_day_tokens = 0
    if day_rows:
        peak = max(day_rows, key=lambda day: day["total_tokens"])
        if peak["total_tokens"] > 0:
            peak_day = peak["day"]
            peak_day_tokens = peak["total_tokens"]

    top_models = [
        {
            "model": model,
            "tokens": tokens,
            "share_percent": (
                _round_half_away_from_zero((tokens / total_window_tokens) * 100.0, digits=1)
                if total_window_tokens > 0
                else 0.0
            ),
        }
        for model, tokens in model_totals.items()
        if model != "unknown" and tokens > 0
    ]
    top_models.sort(key=lambda item: item["tokens"], reverse=True)
    top_models = top_models[:4]

    return {
        "updated_at": updated_at,
        "days": day_rows,
        "totals": {
            "last7_days_tokens": last7_days_tokens,
            "last30_days_tokens": last30_days_tokens,
            "average_daily_tokens": average_daily_tokens,
            "cache_hit_rate_percent": cache_hit_rate_percent,
            "peak_day": peak_day,
            "peak_day_tokens": peak_day_tokens,
        },
        "top_models": top_models,
    }


def _increment_agent_runs(
    daily: dict[str, DailyTotals],
    seen_runs: set[int],
    timestamp_ms: int,
) -> None:
    if timestamp_ms in seen_runs:
        return
    seen_runs.add(timestamp_ms)

    day_key = _day_key_for_timestamp_ms(timestamp_ms)
    if day_key not in daily:
        return
    daily[day_key].agent_runs += 1


def _track_activity(
    daily: dict[str, DailyTotals],
    *,
    last_activity_ms: int | None,
    timestamp_ms: int,
) -> int:
    if last_activity_ms is not None:
        delta = timestamp_ms - last_activity_ms
        if 0 < delta <= MAX_ACTIVITY_GAP_MS:
            day_key = _day_key_for_timestamp_ms(timestamp_ms)
            if day_key in daily:
                daily[day_key].agent_time_ms += delta
    return timestamp_ms


def _find_usage_map(info: dict[str, Any], keys: list[str]) -> dict[str, Any] | None:
    for key in keys:
        value = info.get(key)
        if isinstance(value, dict):
            return value
    return None


def _read_int(data: dict[str, Any], keys: list[str]) -> int:
    for key in keys:
        value = _coerce_int(data.get(key))
        if value is not None:
            return value
    return 0


def _read_timestamp_ms(value: dict[str, Any]) -> int | None:
    raw = value.get("timestamp")
    if isinstance(raw, str):
        return _parse_iso_timestamp_ms(raw)
    numeric = _coerce_int(raw)
    if numeric is None:
        return None
    if 0 < numeric < 1_000_000_000_000:
        return numeric * 1000
    return numeric


def _parse_iso_timestamp_ms(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _day_key_for_timestamp_ms(timestamp_ms: int) -> str | None:
    try:
        utc_dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return utc_dt.astimezone().strftime("%Y-%m-%d")


def _extract_model_from_turn_context(value: dict[str, Any]) -> str | None:
    payload = value.get("payload")
    if not isinstance(payload, dict):
        return None
    payload_model = _as_str(payload.get("model"))
    if payload_model is not None:
        return payload_model

    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    return _as_str(info.get("model"))


def _extract_model_from_token_count(value: dict[str, Any]) -> str | None:
    payload = value.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    info = payload.get("info")
    if not isinstance(info, dict):
        info = {}
    return (
        _as_str(info.get("model"))
        or _as_str(info.get("model_name"))
        or _as_str(payload.get("model"))
        or _as_str(value.get("model"))
    )


def _as_str(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return int(value)
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            return int(trimmed)
        except ValueError:
            try:
                parsed = float(trimmed)
            except ValueError:
                return None
            if math.isfinite(parsed):
                return int(parsed)
    return None


def _round_half_away_from_zero(value: float, digits: int = 0) -> float:
    factor = 10**digits
    scaled = value * factor
    if scaled >= 0:
        rounded = math.floor(scaled + 0.5)
    else:
        rounded = math.ceil(scaled - 0.5)
    return rounded / factor
