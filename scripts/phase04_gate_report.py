#!/usr/bin/env python3
"""Evaluate Phase 04 gate pass/fail from prepared measurement JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "04"


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
    for required in ("P04-G1", "P04-G2", "P04-G3"):
        if required not in targets:
            raise ValueError(f"phase-gates JSON missing target for {required}.")
    return targets


def _reduction_pct(*, baseline: float, candidate: float, metric_label: str) -> float:
    if baseline <= 0:
        raise ValueError(f"{metric_label}: baseline value must be > 0.")
    return ((baseline - candidate) / baseline) * 100.0


def _build_report(
    *,
    targets: dict[str, float],
    benchmark_payload: dict[str, Any],
    recovery_payload: dict[str, Any],
) -> dict[str, Any]:
    baseline_reads = _require_number(
        benchmark_payload,
        "baseline_snapshot_reads_per_turn",
        "benchmark",
    )
    candidate_reads = _require_number(
        benchmark_payload,
        "candidate_snapshot_reads_per_turn",
        "benchmark",
    )
    baseline_writes = _require_number(
        benchmark_payload,
        "baseline_snapshot_writes_per_turn",
        "benchmark",
    )
    candidate_writes = _require_number(
        benchmark_payload,
        "candidate_snapshot_writes_per_turn",
        "benchmark",
    )
    boundary_data_loss = _require_int(
        recovery_payload,
        "crash_recovery_boundary_data_loss_events",
        "recovery",
    )

    read_reduction_pct = _reduction_pct(
        baseline=baseline_reads,
        candidate=candidate_reads,
        metric_label="snapshot read reduction",
    )
    write_reduction_pct = _reduction_pct(
        baseline=baseline_writes,
        candidate=candidate_writes,
        metric_label="snapshot write reduction",
    )

    gate_results = [
        {
            "id": "P04-G1",
            "metric": "snapshot_reads_per_turn_reduction_pct",
            "value": read_reduction_pct,
            "operator": "gte",
            "target": targets["P04-G1"],
            "pass": read_reduction_pct >= targets["P04-G1"],
        },
        {
            "id": "P04-G2",
            "metric": "snapshot_writes_per_turn_reduction_pct",
            "value": write_reduction_pct,
            "operator": "gte",
            "target": targets["P04-G2"],
            "pass": write_reduction_pct >= targets["P04-G2"],
        },
        {
            "id": "P04-G3",
            "metric": "crash_recovery_boundary_data_loss_events",
            "value": boundary_data_loss,
            "operator": "lte",
            "target": targets["P04-G3"],
            "pass": float(boundary_data_loss) <= targets["P04-G3"],
        },
    ]

    return {
        "phase": PHASE_ID,
        "summary": {
            "all_pass": all(bool(gate.get("pass")) for gate in gate_results),
            "baseline_snapshot_reads_per_turn": baseline_reads,
            "candidate_snapshot_reads_per_turn": candidate_reads,
            "baseline_snapshot_writes_per_turn": baseline_writes,
            "candidate_snapshot_writes_per_turn": candidate_writes,
        },
        "gates": gate_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path, help="Path to backend-runtime-benchmark.json")
    parser.add_argument("--recovery", required=True, type=Path, help="Path to recovery-fault-injection.json")
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
        recovery_payload = _load_json(args.recovery)
        report = _build_report(
            targets=targets,
            benchmark_payload=benchmark_payload,
            recovery_payload=recovery_payload,
        )
    except Exception as exc:
        print(f"Phase 04 gate evaluation failed: {exc}")
        return 1

    report_text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text + "\n", encoding="utf-8")

    print(report_text)
    return 0 if bool(report["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())
