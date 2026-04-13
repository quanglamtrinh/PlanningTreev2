#!/usr/bin/env python3
"""Evaluate Phase 03 gate pass/fail from prepared measurement JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "03"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object.")
    return payload


def _require_number(payload: dict[str, Any], key: str, label: str) -> float:
    raw = payload.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{label}: missing or invalid numeric field '{key}'.")
    return float(raw)


def _require_int(payload: dict[str, Any], key: str, label: str) -> int:
    raw = payload.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{label}: missing or invalid integer field '{key}'.")
    return raw


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
    for required in ("P03-G1", "P03-G2", "P03-G3"):
        if required not in targets:
            raise ValueError(f"phase-gates JSON missing target for {required}.")
    return targets


def _build_report(
    *,
    targets: dict[str, float],
    benchmark_payload: dict[str, Any],
    equivalence_payload: dict[str, Any],
    latency_payload: dict[str, Any],
) -> dict[str, Any]:
    baseline = _require_number(
        benchmark_payload,
        "baseline_persisted_events_per_turn",
        "benchmark",
    )
    candidate = _require_number(
        benchmark_payload,
        "candidate_persisted_events_per_turn",
        "benchmark",
    )
    if baseline <= 0:
        raise ValueError("benchmark: 'baseline_persisted_events_per_turn' must be > 0.")

    reduction_pct = ((baseline - candidate) / baseline) * 100.0
    mismatch_count = _require_int(
        equivalence_payload,
        "semantic_mismatch_cases_vs_baseline",
        "equivalence",
    )
    added_latency_p95_ms = _require_number(
        latency_payload,
        "added_stream_latency_p95_ms",
        "latency",
    )

    gate_results = [
        {
            "id": "P03-G1",
            "metric": "persisted_events_per_turn_reduction_pct",
            "value": reduction_pct,
            "operator": "gte",
            "target": targets["P03-G1"],
            "pass": reduction_pct >= targets["P03-G1"],
        },
        {
            "id": "P03-G2",
            "metric": "semantic_mismatch_cases_vs_baseline",
            "value": mismatch_count,
            "operator": "lte",
            "target": targets["P03-G2"],
            "pass": float(mismatch_count) <= targets["P03-G2"],
        },
        {
            "id": "P03-G3",
            "metric": "added_stream_latency_p95_ms",
            "value": added_latency_p95_ms,
            "operator": "lte",
            "target": targets["P03-G3"],
            "pass": added_latency_p95_ms <= targets["P03-G3"],
        },
    ]

    return {
        "phase": PHASE_ID,
        "summary": {
            "all_pass": all(bool(gate.get("pass")) for gate in gate_results),
            "baseline_persisted_events_per_turn": baseline,
            "candidate_persisted_events_per_turn": candidate,
        },
        "gates": gate_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path, help="Path to backend-stream-benchmark.json")
    parser.add_argument(
        "--equivalence",
        required=True,
        type=Path,
        help="Path to golden-replay-equivalence.json",
    )
    parser.add_argument("--latency", required=True, type=Path, help="Path to stream-latency-probe.json")
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
        benchmark_payload = _load_json(args.benchmark)
        equivalence_payload = _load_json(args.equivalence)
        latency_payload = _load_json(args.latency)
        report = _build_report(
            targets=targets,
            benchmark_payload=benchmark_payload,
            equivalence_payload=equivalence_payload,
            latency_payload=latency_payload,
        )
    except Exception as exc:
        print(f"Phase 03 gate evaluation failed: {exc}")
        return 1

    report_text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text + "\n", encoding="utf-8")

    print(report_text)
    return 0 if bool(report["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())
