#!/usr/bin/env python3
"""Produce deterministic Phase 06 interactive stream lag evidence JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("latency sample set must not be empty.")
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _build_payload(*, sample_size: int, base_lag_ms: float, jitter_window_ms: float) -> dict[str, Any]:
    if sample_size <= 0:
        raise ValueError("sample_size must be > 0.")
    if base_lag_ms < 0 or jitter_window_ms < 0:
        raise ValueError("base_lag_ms and jitter_window_ms must be >= 0.")

    # Deterministic sequence: triangle-wave style jitter around base lag.
    samples = []
    for idx in range(sample_size):
        offset = abs((idx % 14) - 7) / 7.0
        lag = base_lag_ms + (offset * jitter_window_ms)
        samples.append(round(lag, 3))
    samples_sorted = sorted(samples)
    p95 = round(_percentile(samples_sorted, 95.0), 3)

    return {
        "run_meta": {
            "phase": "06",
            "scenario": "interactive_stream_smoke",
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "harness": "deterministic_interactive_latency_model_v1",
            "inputs": {
                "sample_size": sample_size,
                "base_lag_ms": base_lag_ms,
                "jitter_window_ms": jitter_window_ms,
            },
        },
        "candidate_metrics": {
            "visible_stream_lag_p95_ms": p95,
            "sample_count": sample_size,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=100, help="Number of latency samples.")
    parser.add_argument("--base-lag-ms", type=float, default=90.0, help="Base visible lag in milliseconds.")
    parser.add_argument(
        "--jitter-window-ms",
        type=float,
        default=10.0,
        help="Deterministic jitter amplitude window in milliseconds.",
    )
    parser.add_argument("--out", required=True, type=Path, help="Output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _build_payload(
        sample_size=int(args.sample_size),
        base_lag_ms=float(args.base_lag_ms),
        jitter_window_ms=float(args.jitter_window_ms),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
