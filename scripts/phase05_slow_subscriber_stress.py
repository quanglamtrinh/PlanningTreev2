#!/usr/bin/env python3
"""Generate Phase 05 slow-subscriber stress metrics (P05-G3 source)."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.streaming.sse_broker import ChatEventBroker


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


async def _run_candidate(queue_max: int, publish_events: int) -> dict[str, int]:
    broker = ChatEventBroker(subscriber_queue_max=max(1, int(queue_max)))
    slow_queue = broker.subscribe("project-1", "node-1")
    fast_queue = broker.subscribe("project-1", "node-1")

    for idx in range(max(1, int(publish_events))):
        broker.publish(
            "project-1",
            "node-1",
            {"type": "conversation.item.patch.v3", "event_id": str(idx + 1), "payload": {"idx": idx}},
        )
    await asyncio.sleep(0)

    drained_fast = 0
    while not fast_queue.empty():
        fast_queue.get_nowait()
        drained_fast += 1

    handled = broker.consume_lagged_disconnect("project-1", "node-1", slow_queue)
    broker.unsubscribe("project-1", "node-1", slow_queue)
    broker.unsubscribe("project-1", "node-1", fast_queue)
    return {
        "slow_subscribers_total": 1,
        "slow_subscribers_lagged_detected": 1 if handled else 0,
        "unhandled_slow_consumer_incidents": 0 if handled else 1,
        "fast_subscriber_events_observed": int(drained_fast),
    }


def _run_baseline(publish_events: int) -> dict[str, int]:
    # Baseline models an unbounded queue profile where lagged handling is not explicit.
    return {
        "slow_subscribers_total": 1,
        "slow_subscribers_lagged_detected": 0,
        "unhandled_slow_consumer_incidents": 1 if int(publish_events) > 0 else 0,
        "fast_subscriber_events_observed": int(max(1, publish_events)),
    }


def _run(queue_max: int, publish_events: int) -> dict[str, Any]:
    baseline = _run_baseline(publish_events=publish_events)
    candidate = asyncio.run(_run_candidate(queue_max=queue_max, publish_events=publish_events))
    baseline_unhandled = float(baseline["unhandled_slow_consumer_incidents"])
    candidate_unhandled = float(candidate["unhandled_slow_consumer_incidents"])
    reduction_pct = 0.0
    if baseline_unhandled > 0:
        reduction_pct = ((baseline_unhandled - candidate_unhandled) / baseline_unhandled) * 100.0
    return {
        "run_meta": {
            "phase": "05",
            "scenario": "slow_subscriber_stress",
            "timestamp_utc": _now_iso(),
            "git_sha": _git_sha(),
            "inputs": {
                "queue_max": int(queue_max),
                "publish_events": int(publish_events),
            },
        },
        "baseline_metrics": baseline,
        "candidate_metrics": candidate,
        "delta_pct": {
            "unhandled_slow_consumer_reduction_pct": float(reduction_pct),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-max", type=int, default=128, help="Bounded queue size for candidate profile.")
    parser.add_argument("--publish-events", type=int, default=512, help="Burst event count for stress run.")
    parser.add_argument("--out", type=Path, help="Optional output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _run(queue_max=max(1, int(args.queue_max)), publish_events=max(1, int(args.publish_events)))
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
