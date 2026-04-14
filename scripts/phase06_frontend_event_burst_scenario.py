#!/usr/bin/env python3
"""Produce deterministic Phase 06 burst-apply evidence JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _build_payload(*, burst_events: int, candidate_apply_calls: int) -> dict[str, Any]:
    if burst_events <= 0:
        raise ValueError("burst_events must be > 0.")
    if candidate_apply_calls <= 0:
        raise ValueError("candidate_apply_calls must be > 0.")
    if candidate_apply_calls > burst_events:
        raise ValueError("candidate_apply_calls cannot exceed burst_events.")

    reduction_pct = ((burst_events - candidate_apply_calls) / float(burst_events)) * 100.0
    return {
        "run_meta": {
            "phase": "06",
            "scenario": "frontend_event_burst_scenario",
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "harness": "deterministic_frame_batch_model_v1",
            "inputs": {
                "burst_events": burst_events,
                "candidate_apply_calls": candidate_apply_calls,
            },
        },
        "baseline_metrics": {
            "apply_calls_per_burst": float(burst_events),
        },
        "candidate_metrics": {
            "apply_calls_per_burst": float(candidate_apply_calls),
            "apply_calls_per_burst_reduction_pct": reduction_pct,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--burst-events", type=int, default=400, help="Baseline apply count in burst scenario.")
    parser.add_argument(
        "--candidate-apply-calls",
        type=int,
        default=140,
        help="Candidate apply count after frame batching.",
    )
    parser.add_argument("--out", required=True, type=Path, help="Output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _build_payload(
        burst_events=int(args.burst_events),
        candidate_apply_calls=int(args.candidate_apply_calls),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
