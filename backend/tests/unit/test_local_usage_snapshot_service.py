from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from backend.services import local_usage_snapshot_service as local_usage_snapshot_module
from backend.services.local_usage_snapshot_service import (
    MAX_LINE_BYTES,
    LocalUsageSnapshotService,
)


def _today_day_key() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _timestamp_ms_for_day(
    day_key: str,
    *,
    hour: int,
    minute: int,
    second: int,
) -> int:
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


def _write_session_file(
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


def _token_count_event(
    timestamp_ms: int,
    *,
    total: dict[str, int] | None = None,
    last: dict[str, int] | None = None,
    info_model: str | None = None,
    info_model_name: str | None = None,
    payload_model: str | None = None,
    root_model: str | None = None,
) -> str:
    info: dict[str, object] = {}
    if total is not None:
        info["total_token_usage"] = total
    if last is not None:
        info["last_token_usage"] = last
    if info_model is not None:
        info["model"] = info_model
    if info_model_name is not None:
        info["model_name"] = info_model_name

    payload: dict[str, object] = {
        "type": "token_count",
        "info": info,
    }
    if payload_model is not None:
        payload["model"] = payload_model

    event: dict[str, object] = {
        "timestamp": timestamp_ms,
        "payload": payload,
    }
    if root_model is not None:
        event["model"] = root_model
    return json.dumps(event)


def _turn_context_event(model: str) -> str:
    return json.dumps(
        {
            "type": "turn_context",
            "payload": {"model": model},
        }
    )


def _assistant_response_event(timestamp_ms: int, text: str) -> str:
    return json.dumps(
        {
            "timestamp": timestamp_ms,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        }
    )


def _day_row(snapshot: dict) -> dict:
    assert snapshot["days"]
    return snapshot["days"][-1]


def test_total_only_stream_aggregation(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=0, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=0, second=5)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts1,
                total={
                    "input_tokens": 10,
                    "cached_input_tokens": 1,
                    "output_tokens": 5,
                },
            ),
            _token_count_event(
                ts2,
                total={
                    "input_tokens": 25,
                    "cached_input_tokens": 4,
                    "output_tokens": 8,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)

    assert row["input_tokens"] == 25
    assert row["cached_input_tokens"] == 4
    assert row["output_tokens"] == 8
    assert row["total_tokens"] == 33


def test_mixed_last_and_total_usage_does_not_double_count(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=1, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=1, second=1)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts1,
                last={
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                },
            ),
            _token_count_event(
                ts2,
                total={
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5


def test_last_deltas_between_total_snapshots_are_counted_once(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=2, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=2, second=1)
    ts3 = _timestamp_ms_for_day(day_key, hour=12, minute=2, second=2)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts1,
                total={
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                },
            ),
            _token_count_event(
                ts2,
                last={
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            ),
            _token_count_event(
                ts3,
                total={
                    "input_tokens": 12,
                    "cached_input_tokens": 0,
                    "output_tokens": 6,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["input_tokens"] == 12
    assert row["output_tokens"] == 6


def test_malformed_json_line_is_skipped(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=3, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=3, second=1)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts1,
                total={
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            ),
            "{broken-json",
            _token_count_event(
                ts2,
                total={
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["input_tokens"] == 2
    assert row["output_tokens"] == 2


def test_oversized_line_is_skipped(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts = _timestamp_ms_for_day(day_key, hour=12, minute=4, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            "x" * (MAX_LINE_BYTES + 1),
            _token_count_event(
                ts,
                total={
                    "input_tokens": 3,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["input_tokens"] == 3
    assert row["output_tokens"] == 1


def test_unreadable_file_is_skipped(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    year, month, day = day_key.split("-")
    day_dir = codex_home / "sessions" / year / month / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "broken.jsonl").mkdir()

    ts = _timestamp_ms_for_day(day_key, hour=12, minute=5, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts,
                total={
                    "input_tokens": 4,
                    "cached_input_tokens": 1,
                    "output_tokens": 2,
                },
            )
        ],
        name="valid.jsonl",
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["input_tokens"] == 4
    assert row["output_tokens"] == 2


def test_run_counting_from_assistant_events(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=6, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=6, second=5)
    _write_session_file(
        codex_home,
        day_key,
        [
            _assistant_response_event(ts1, "a"),
            _assistant_response_event(ts2, "b"),
            _assistant_response_event(ts2, "duplicate timestamp"),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["agent_runs"] == 2


def test_activity_gap_cap_for_agent_time(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts1 = _timestamp_ms_for_day(day_key, hour=12, minute=0, second=0)
    ts2 = _timestamp_ms_for_day(day_key, hour=12, minute=10, second=0)
    ts3 = _timestamp_ms_for_day(day_key, hour=12, minute=10, second=10)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts1,
                total={
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            ),
            _token_count_event(
                ts2,
                total={
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
            ),
            _token_count_event(
                ts3,
                total={
                    "input_tokens": 3,
                    "cached_input_tokens": 0,
                    "output_tokens": 3,
                },
            ),
        ],
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    row = _day_row(snapshot)
    assert row["agent_time_ms"] == 10_000


def test_model_attribution_and_top_models_sorting(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    base_ts = _timestamp_ms_for_day(day_key, hour=13, minute=0, second=0)

    _write_session_file(
        codex_home,
        day_key,
        [
            _turn_context_event("gpt-5"),
            _token_count_event(
                base_ts,
                total={
                    "input_tokens": 30,
                    "cached_input_tokens": 0,
                    "output_tokens": 10,
                },
            ),
        ],
        name="a.jsonl",
    )
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                base_ts + 1_000,
                total={
                    "input_tokens": 20,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                },
                info_model_name="o3-mini",
            ),
        ],
        name="b.jsonl",
    )
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                base_ts + 2_000,
                total={
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                },
                payload_model="gpt-4.1",
            ),
        ],
        name="c.jsonl",
    )
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                base_ts + 3_000,
                total={
                    "input_tokens": 8,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
                root_model="o1",
            ),
        ],
        name="d.jsonl",
    )
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                base_ts + 4_000,
                total={
                    "input_tokens": 6,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            ),
        ],
        name="e.jsonl",
    )

    snapshot = LocalUsageSnapshotService(codex_home=codex_home).read_snapshot(days=1)
    top_models = snapshot["top_models"]

    assert [entry["model"] for entry in top_models] == [
        "gpt-5",
        "o3-mini",
        "gpt-4.1",
        "o1",
    ]
    assert [entry["tokens"] for entry in top_models] == [40, 25, 15, 10]
    assert all(entry["model"] != "unknown" for entry in top_models)


def test_days_clamp_and_default_behavior(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    service = LocalUsageSnapshotService(codex_home=codex_home)

    assert len(service.read_snapshot()["days"]) == 30
    assert len(service.read_snapshot(days=0)["days"]) == 1
    assert len(service.read_snapshot(days=-5)["days"]) == 1
    assert len(service.read_snapshot(days=120)["days"]) == 90


def test_cache_hit_within_ttl_does_not_rescan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts = _timestamp_ms_for_day(day_key, hour=14, minute=0, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts,
                total={
                    "input_tokens": 10,
                    "cached_input_tokens": 1,
                    "output_tokens": 4,
                },
            )
        ],
    )

    service = LocalUsageSnapshotService(codex_home=codex_home)
    scan_calls = {"count": 0}
    original_scan_file = local_usage_snapshot_module._scan_file

    def wrapped_scan_file(*args, **kwargs):
        scan_calls["count"] += 1
        return original_scan_file(*args, **kwargs)

    now = {"value": 100.0}
    monkeypatch.setattr(local_usage_snapshot_module.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(local_usage_snapshot_module, "_scan_file", wrapped_scan_file)

    service.read_snapshot(days=1)
    now["value"] = 110.0
    service.read_snapshot(days=1)

    assert scan_calls["count"] == 1


def test_cache_stale_after_ttl_triggers_recompute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts = _timestamp_ms_for_day(day_key, hour=14, minute=10, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts,
                total={
                    "input_tokens": 12,
                    "cached_input_tokens": 1,
                    "output_tokens": 3,
                },
            )
        ],
    )

    service = LocalUsageSnapshotService(codex_home=codex_home)
    scan_calls = {"count": 0}
    original_scan_file = local_usage_snapshot_module._scan_file

    def wrapped_scan_file(*args, **kwargs):
        scan_calls["count"] += 1
        return original_scan_file(*args, **kwargs)

    now = {"value": 200.0}
    monkeypatch.setattr(local_usage_snapshot_module.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(local_usage_snapshot_module, "_scan_file", wrapped_scan_file)

    service.read_snapshot(days=1)
    now["value"] = 231.0
    service.read_snapshot(days=1)

    assert scan_calls["count"] == 2


def test_single_flight_concurrent_requests_compute_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts = _timestamp_ms_for_day(day_key, hour=14, minute=20, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts,
                total={
                    "input_tokens": 8,
                    "cached_input_tokens": 1,
                    "output_tokens": 2,
                },
            )
        ],
    )

    service = LocalUsageSnapshotService(codex_home=codex_home)
    scan_calls = {"count": 0}
    original_scan_file = local_usage_snapshot_module._scan_file

    def wrapped_scan_file(*args, **kwargs):
        scan_calls["count"] += 1
        time.sleep(0.05)
        return original_scan_file(*args, **kwargs)

    monkeypatch.setattr(local_usage_snapshot_module, "_scan_file", wrapped_scan_file)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(service.read_snapshot, 1) for _ in range(4)]
        results = [future.result(timeout=5) for future in futures]

    assert scan_calls["count"] == 1
    assert all(len(result["days"]) == 1 for result in results)


def test_cache_keys_are_isolated_by_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    day_key = _today_day_key()
    ts = _timestamp_ms_for_day(day_key, hour=14, minute=30, second=0)
    _write_session_file(
        codex_home,
        day_key,
        [
            _token_count_event(
                ts,
                total={
                    "input_tokens": 5,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            )
        ],
    )

    service = LocalUsageSnapshotService(codex_home=codex_home)
    scan_calls = {"count": 0}
    original_scan_file = local_usage_snapshot_module._scan_file

    def wrapped_scan_file(*args, **kwargs):
        scan_calls["count"] += 1
        return original_scan_file(*args, **kwargs)

    monkeypatch.setattr(local_usage_snapshot_module, "_scan_file", wrapped_scan_file)

    service.read_snapshot(days=1)
    service.read_snapshot(days=7)
    service.read_snapshot(days=1)

    assert scan_calls["count"] == 2


def test_cache_keys_are_isolated_by_sessions_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home_a = tmp_path / ".codex-a"
    codex_home_b = tmp_path / ".codex-b"
    day_key = _today_day_key()
    ts_a = _timestamp_ms_for_day(day_key, hour=14, minute=40, second=0)
    ts_b = _timestamp_ms_for_day(day_key, hour=14, minute=40, second=1)

    _write_session_file(
        codex_home_a,
        day_key,
        [
            _token_count_event(
                ts_a,
                total={
                    "input_tokens": 3,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            )
        ],
    )
    _write_session_file(
        codex_home_b,
        day_key,
        [
            _token_count_event(
                ts_b,
                total={
                    "input_tokens": 7,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
            )
        ],
    )

    service = LocalUsageSnapshotService(codex_home=codex_home_a)
    scan_calls = {"count": 0}
    original_scan_file = local_usage_snapshot_module._scan_file

    def wrapped_scan_file(*args, **kwargs):
        scan_calls["count"] += 1
        return original_scan_file(*args, **kwargs)

    roots = [
        codex_home_a / "sessions",
        codex_home_b / "sessions",
        codex_home_a / "sessions",
    ]
    index = {"value": 0}

    def fake_resolve_sessions_root() -> Path:
        root = roots[min(index["value"], len(roots) - 1)]
        index["value"] += 1
        return root

    monkeypatch.setattr(local_usage_snapshot_module, "_scan_file", wrapped_scan_file)
    monkeypatch.setattr(service, "_resolve_sessions_root", fake_resolve_sessions_root)

    service.read_snapshot(days=1)
    service.read_snapshot(days=1)
    service.read_snapshot(days=1)

    assert scan_calls["count"] == 2
