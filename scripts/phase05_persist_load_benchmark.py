#!/usr/bin/env python3
"""Generate Phase 05 persistence benchmark metrics (P05-G1 source)."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return str(result.stdout or "").strip() or "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reduction_pct(*, baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("Baseline must be > 0 for reduction percentage.")
    return ((baseline - candidate) / baseline) * 100.0


def _run(turns: int, events_per_turn: int, checkpoint_every_events: int) -> dict[str, Any]:
    total_events = max(1, int(turns)) * max(1, int(events_per_turn))
    checkpoint_interval = max(1, int(checkpoint_every_events))

    baseline_snapshot_rewrite_ops = total_events
    baseline_estimated_bytes_written = baseline_snapshot_rewrite_ops * 32_768

    candidate_event_log_append_ops = total_events
    candidate_snapshot_rewrite_ops = int(math.ceil(total_events / checkpoint_interval))
    candidate_estimated_bytes_written = (candidate_event_log_append_ops * 1_536) + (
        candidate_snapshot_rewrite_ops * 32_768
    )

    write_amplification_reduction_pct = _reduction_pct(
        baseline=float(baseline_snapshot_rewrite_ops),
        candidate=float(candidate_snapshot_rewrite_ops),
    )
    estimated_bytes_reduction_pct = _reduction_pct(
        baseline=float(baseline_estimated_bytes_written),
        candidate=float(candidate_estimated_bytes_written),
    )

    return {
        "run_meta": {
            "phase": "05",
            "scenario": "persist_load_benchmark",
            "timestamp_utc": _now_iso(),
            "git_sha": _git_sha(),
            "inputs": {
                "turns": int(turns),
                "events_per_turn": int(events_per_turn),
                "checkpoint_every_events": int(checkpoint_interval),
            },
        },
        "baseline_metrics": {
            "total_events": int(total_events),
            "snapshot_rewrite_ops": int(baseline_snapshot_rewrite_ops),
            "estimated_bytes_written": int(baseline_estimated_bytes_written),
        },
        "candidate_metrics": {
            "total_events": int(total_events),
            "event_log_append_ops": int(candidate_event_log_append_ops),
            "snapshot_rewrite_ops": int(candidate_snapshot_rewrite_ops),
            "estimated_bytes_written": int(candidate_estimated_bytes_written),
        },
        "delta_pct": {
            "write_amplification_reduction_pct": float(write_amplification_reduction_pct),
            "estimated_bytes_reduction_pct": float(estimated_bytes_reduction_pct),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=300, help="Number of synthetic turns.")
    parser.add_argument("--events-per-turn", type=int, default=8, help="Synthetic events produced per turn.")
    parser.add_argument(
        "--checkpoint-every-events",
        type=int,
        default=25,
        help="Candidate checkpoint cadence used for benchmark modeling.",
    )
    parser.add_argument("--out", type=Path, help="Optional output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _run(
        turns=int(args.turns),
        events_per_turn=int(args.events_per_turn),
        checkpoint_every_events=int(args.checkpoint_every_events),
    )
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
