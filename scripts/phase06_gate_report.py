#!/usr/bin/env python3
"""Evaluate Phase 06 gate pass/fail from frontend batching measurement JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "06"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object.")
    return payload


def _require_number(payload: dict[str, Any], dotted_key: str, label: str) -> float:
    current: Any = payload
    for token in dotted_key.split("."):
        if not isinstance(current, dict):
            raise ValueError(f"{label}: missing object path '{dotted_key}'.")
        current = current.get(token)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise ValueError(f"{label}: missing or invalid numeric field '{dotted_key}'.")
    return float(current)


def _find_gate_targets(gate_file: Path) -> dict[str, float]:
    payload = _load_json(gate_file)
    phases = payload.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("phase-gates JSON missing 'phases' object.")
    phase_gates = phases.get(PHASE_ID)
    if not isinstance(phase_gates, list):
        raise ValueError(f"phase-gates JSON missing phase '{PHASE_ID}'.")

    targets: dict[str, float] = {}
    for gate in phase_gates:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id") or "").strip()
        target = gate.get("target")
        if gate_id and isinstance(target, (int, float)) and not isinstance(target, bool):
            targets[gate_id] = float(target)
    for required in ("P06-G1", "P06-G2", "P06-G3"):
        if required not in targets:
            raise ValueError(f"phase-gates JSON missing target for {required}.")
    return targets


def _build_report(
    *,
    targets: dict[str, float],
    burst_payload: dict[str, Any],
    interactive_payload: dict[str, Any],
    order_payload: dict[str, Any],
) -> dict[str, Any]:
    apply_calls_per_burst_reduction_pct = _require_number(
        burst_payload,
        "candidate_metrics.apply_calls_per_burst_reduction_pct",
        "frontend_event_burst_scenario",
    )
    visible_stream_lag_p95_ms = _require_number(
        interactive_payload,
        "candidate_metrics.visible_stream_lag_p95_ms",
        "interactive_stream_smoke",
    )
    batch_order_violations = _require_number(
        order_payload,
        "candidate_metrics.batch_order_violations",
        "apply_order_integration_tests",
    )

    gate_results = [
        {
            "id": "P06-G1",
            "metric": "apply_calls_per_burst_reduction_pct",
            "value": apply_calls_per_burst_reduction_pct,
            "operator": "gte",
            "target": targets["P06-G1"],
            "pass": apply_calls_per_burst_reduction_pct >= targets["P06-G1"],
        },
        {
            "id": "P06-G2",
            "metric": "visible_stream_lag_p95_ms",
            "value": visible_stream_lag_p95_ms,
            "operator": "lte",
            "target": targets["P06-G2"],
            "pass": visible_stream_lag_p95_ms <= targets["P06-G2"],
        },
        {
            "id": "P06-G3",
            "metric": "batch_order_violations",
            "value": batch_order_violations,
            "operator": "lte",
            "target": targets["P06-G3"],
            "pass": batch_order_violations <= targets["P06-G3"],
        },
    ]

    return {
        "phase": PHASE_ID,
        "summary": {
            "all_pass": all(bool(gate.get("pass")) for gate in gate_results),
            "apply_calls_per_burst_reduction_pct": apply_calls_per_burst_reduction_pct,
            "visible_stream_lag_p95_ms": visible_stream_lag_p95_ms,
            "batch_order_violations": batch_order_violations,
        },
        "gates": gate_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--burst",
        required=True,
        type=Path,
        help="Path to frontend-event-burst-scenario JSON.",
    )
    parser.add_argument(
        "--interactive",
        required=True,
        type=Path,
        help="Path to interactive-stream-smoke JSON.",
    )
    parser.add_argument(
        "--order",
        required=True,
        type=Path,
        help="Path to apply-order-integration-tests JSON.",
    )
    parser.add_argument(
        "--gates-file",
        type=Path,
        default=Path("docs/render/system-freeze/phase-gates-v1.json"),
        help="Path to phase gate definitions.",
    )
    parser.add_argument("--out", type=Path, help="Optional output JSON path.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        targets = _find_gate_targets(args.gates_file)
        burst_payload = _load_json(args.burst)
        interactive_payload = _load_json(args.interactive)
        order_payload = _load_json(args.order)
        report = _build_report(
            targets=targets,
            burst_payload=burst_payload,
            interactive_payload=interactive_payload,
            order_payload=order_payload,
        )
    except Exception as exc:
        print(f"Phase 06 gate evaluation failed: {exc}")
        return 1

    report_text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text + "\n", encoding="utf-8")

    print(report_text)
    return 0 if bool(report["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())
