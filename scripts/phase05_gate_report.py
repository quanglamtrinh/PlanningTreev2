#!/usr/bin/env python3
"""Evaluate Phase 05 gate pass/fail from benchmark/profile/stress JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "05"


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
    for required in ("P05-G1", "P05-G2", "P05-G3"):
        if required not in targets:
            raise ValueError(f"phase-gates JSON missing target for {required}.")
    return targets


def _build_report(
    *,
    targets: dict[str, float],
    persist_payload: dict[str, Any],
    broker_payload: dict[str, Any],
    slow_payload: dict[str, Any],
) -> dict[str, Any]:
    write_amp_reduction_pct = _require_number(
        persist_payload,
        "delta_pct.write_amplification_reduction_pct",
        "persist_load_benchmark",
    )
    broker_alloc_reduction_pct = _require_number(
        broker_payload,
        "delta_pct.broker_publish_allocation_reduction_pct",
        "broker_profile_run",
    )
    unhandled_slow_consumer_incidents = _require_number(
        slow_payload,
        "candidate_metrics.unhandled_slow_consumer_incidents",
        "slow_subscriber_stress",
    )

    gate_results = [
        {
            "id": "P05-G1",
            "metric": "write_amplification_reduction_pct",
            "value": write_amp_reduction_pct,
            "operator": "gte",
            "target": targets["P05-G1"],
            "pass": write_amp_reduction_pct >= targets["P05-G1"],
        },
        {
            "id": "P05-G2",
            "metric": "broker_publish_allocation_reduction_pct",
            "value": broker_alloc_reduction_pct,
            "operator": "gte",
            "target": targets["P05-G2"],
            "pass": broker_alloc_reduction_pct >= targets["P05-G2"],
        },
        {
            "id": "P05-G3",
            "metric": "unhandled_slow_consumer_incidents",
            "value": unhandled_slow_consumer_incidents,
            "operator": "lte",
            "target": targets["P05-G3"],
            "pass": unhandled_slow_consumer_incidents <= targets["P05-G3"],
        },
    ]

    return {
        "phase": PHASE_ID,
        "summary": {
            "all_pass": all(bool(gate.get("pass")) for gate in gate_results),
            "write_amplification_reduction_pct": write_amp_reduction_pct,
            "broker_publish_allocation_reduction_pct": broker_alloc_reduction_pct,
            "unhandled_slow_consumer_incidents": unhandled_slow_consumer_incidents,
        },
        "gates": gate_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", required=True, type=Path, help="Path to persist-load benchmark JSON.")
    parser.add_argument("--broker", required=True, type=Path, help="Path to broker-profile-run JSON.")
    parser.add_argument("--slow", required=True, type=Path, help="Path to slow-subscriber-stress JSON.")
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
        persist_payload = _load_json(args.persist)
        broker_payload = _load_json(args.broker)
        slow_payload = _load_json(args.slow)
        report = _build_report(
            targets=targets,
            persist_payload=persist_payload,
            broker_payload=broker_payload,
            slow_payload=slow_payload,
        )
    except Exception as exc:
        print(f"Phase 05 gate evaluation failed: {exc}")
        return 1

    report_text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text + "\n", encoding="utf-8")

    print(report_text)
    return 0 if bool(report["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())
