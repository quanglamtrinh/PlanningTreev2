#!/usr/bin/env python3
"""Generate Phase 05 broker publish profile metrics (P05-G2 source)."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
import tracemalloc
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


def _sample_event() -> dict[str, Any]:
    return {
        "type": "conversation.item.patch.v3",
        "event_id": "999",
        "payload": {
            "itemId": "item-1",
            "patch": {
                "kind": "message",
                "textAppend": "delta",
                "metadata": {
                    "flags": ["a", "b", "c"],
                    "counts": {"x": 1, "y": 2},
                },
            },
        },
    }


def _profile_baseline(*, subscribers: int, iterations: int) -> dict[str, float]:
    event = _sample_event()
    tracemalloc.start()
    started = time.perf_counter()
    sink = 0
    for _ in range(iterations):
        for _idx in range(subscribers):
            cloned = copy.deepcopy(event)
            sink += len(str(cloned.get("type") or ""))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if sink < 0:
        raise RuntimeError("unreachable")
    return {
        "elapsed_ms": float(elapsed_ms),
        "peak_alloc_bytes": float(peak),
        "allocation_copy_ops": float(iterations * subscribers),
    }


def _profile_candidate(*, subscribers: int, iterations: int) -> dict[str, float]:
    event = _sample_event()
    tracemalloc.start()
    started = time.perf_counter()
    sink = 0
    for _ in range(iterations):
        cloned_once = copy.deepcopy(event)
        for _idx in range(subscribers):
            sink += len(str(cloned_once.get("type") or ""))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if sink < 0:
        raise RuntimeError("unreachable")
    return {
        "elapsed_ms": float(elapsed_ms),
        "peak_alloc_bytes": float(peak),
        "allocation_copy_ops": float(iterations),
    }


def _reduction_pct(*, baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("Baseline must be > 0 for reduction percentage.")
    return ((baseline - candidate) / baseline) * 100.0


def _run(subscribers: int, iterations: int) -> dict[str, Any]:
    baseline = _profile_baseline(subscribers=subscribers, iterations=iterations)
    candidate = _profile_candidate(subscribers=subscribers, iterations=iterations)
    allocation_reduction_pct = _reduction_pct(
        baseline=float(baseline["allocation_copy_ops"]),
        candidate=float(candidate["allocation_copy_ops"]),
    )
    elapsed_reduction_pct = _reduction_pct(
        baseline=float(baseline["elapsed_ms"]),
        candidate=float(candidate["elapsed_ms"]),
    )
    return {
        "run_meta": {
            "phase": "05",
            "scenario": "broker_profile_run",
            "timestamp_utc": _now_iso(),
            "git_sha": _git_sha(),
            "inputs": {
                "subscribers": int(subscribers),
                "iterations": int(iterations),
            },
        },
        "baseline_metrics": baseline,
        "candidate_metrics": candidate,
        "delta_pct": {
            "broker_publish_allocation_reduction_pct": float(allocation_reduction_pct),
            "broker_publish_elapsed_reduction_pct": float(elapsed_reduction_pct),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscribers", type=int, default=20, help="Number of subscribers per publish.")
    parser.add_argument("--iterations", type=int, default=1200, help="Number of publish iterations.")
    parser.add_argument("--out", type=Path, help="Optional output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _run(subscribers=max(1, int(args.subscribers)), iterations=max(1, int(args.iterations)))
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
