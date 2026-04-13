#!/usr/bin/env python3
"""Evaluate Phase 07 gate pass/fail from source evidence JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_ID = "07"
SOURCE = "phase07_gate_report"
DEFAULT_OUTPUT = Path("docs/render/phases/phase-07-state-shape-hot-path/evidence/phase07-gate-report.json")
DEFAULT_BASELINE = Path("docs/render/phases/phase-07-state-shape-hot-path/evidence/baseline-manifest-v1.json")
DEFAULT_GATES_FILE = Path("docs/render/system-freeze/phase-gates-v1.json")
ALLOWED_OPERATORS = {"gte", "lte", "eq"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object.")
    return payload


def _evaluate(operator: str, value: float, target: float) -> bool:
    if operator == "gte":
        return value >= target
    if operator == "lte":
        return value <= target
    if operator == "eq":
        return value == target
    raise ValueError(f"Unsupported operator: {operator}")


def _phase_gates(gates_file: Path) -> list[dict[str, Any]]:
    payload = _load_json(gates_file)
    phases = payload.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("phase-gates JSON missing 'phases' object.")
    phase_gates = phases.get(PHASE_ID)
    if not isinstance(phase_gates, list):
        raise ValueError(f"phase-gates JSON missing phase '{PHASE_ID}'.")

    resolved: list[dict[str, Any]] = []
    for gate in phase_gates:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id") or "").strip()
        metric = str(gate.get("metric") or "").strip()
        source = str(gate.get("source") or "").strip()
        operator = str(gate.get("operator") or "").strip()
        target = gate.get("target")
        if not gate_id or not metric or not source:
            raise ValueError("phase-gates contains invalid gate record for phase 07.")
        if operator not in ALLOWED_OPERATORS:
            raise ValueError(f"{gate_id}: unsupported operator '{operator}'.")
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            raise ValueError(f"{gate_id}: missing numeric target.")
        resolved.append(
            {
                "id": gate_id,
                "metric": metric,
                "source": source,
                "operator": operator,
                "target": float(target),
            }
        )

    required_sources = {"state_hot_path_benchmark", "state_hot_path_trace", "reducer_identity_tests"}
    actual_sources = {str(g["source"]) for g in resolved}
    missing = sorted(required_sources - actual_sources)
    if missing:
        raise ValueError(f"phase-gates missing required phase 07 sources: {', '.join(missing)}")
    return resolved


def _baseline_metadata(baseline_path: Path | None) -> dict[str, Any] | None:
    if baseline_path is None:
        return None
    if not baseline_path.exists():
        raise ValueError(f"Baseline file not found: {baseline_path}")
    payload = _load_json(baseline_path)
    metadata: dict[str, Any] = {}
    baseline = payload.get("baseline")
    if isinstance(baseline, dict):
        metadata.update(baseline)
    if "version" in payload:
        metadata["manifest_version"] = payload["version"]
    metadata["manifest_path"] = baseline_path.as_posix()
    return metadata


def _load_source_metric(*, artifact_path: Path, gate: dict[str, Any]) -> float:
    if not artifact_path.exists():
        raise ValueError(f"Missing source artifact for {gate['id']}: {artifact_path.as_posix()}")
    payload = _load_json(artifact_path)
    source = str(payload.get("source") or "").strip()
    if source != str(gate["source"]):
        raise ValueError(
            f"{artifact_path.as_posix()}: source mismatch, expected '{gate['source']}', got '{source or 'missing'}'."
        )
    metric = str(payload.get("metric") or "").strip()
    if metric != str(gate["metric"]):
        raise ValueError(
            f"{artifact_path.as_posix()}: metric mismatch, expected '{gate['metric']}', got '{metric or 'missing'}'."
        )
    value = payload.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{artifact_path.as_posix()}: missing numeric field 'value' for metric '{metric}'.")
    return float(value)


def _build_report(
    *,
    gates: list[dict[str, Any]],
    evidence_dir: Path,
    baseline_path: Path | None,
    candidate_path: Path | None,
) -> dict[str, Any]:
    gate_results: list[dict[str, Any]] = []
    pass_count = 0
    for gate in gates:
        artifact_path = evidence_dir / f"{gate['source']}.json"
        value = _load_source_metric(artifact_path=artifact_path, gate=gate)
        passed = _evaluate(str(gate["operator"]), value, float(gate["target"]))
        if passed:
            pass_count += 1
        gate_results.append(
            {
                "id": str(gate["id"]),
                "source": str(gate["source"]),
                "metric": str(gate["metric"]),
                "value": value,
                "operator": str(gate["operator"]),
                "target": float(gate["target"]),
                "pass": passed,
                "artifact": artifact_path.as_posix(),
            }
        )

    all_pass = pass_count == len(gates)
    payload: dict[str, Any] = {
        "phase": PHASE_ID,
        "generated_at": _now_iso(),
        "source": SOURCE,
        "status": "pass" if all_pass else "fail",
        "metric": "phase07_gate_pass_count",
        "value": float(pass_count),
        "target": float(len(gates)),
        "operator": "eq",
        "pass": all_pass,
        "context": {
            "evidence_dir": evidence_dir.as_posix(),
            "candidate_path": candidate_path.as_posix() if candidate_path is not None else None,
            "gate_count": len(gates),
        },
        "summary": {
            "all_pass": all_pass,
            "pass_count": pass_count,
            "total_gates": len(gates),
        },
        "gates": gate_results,
    }
    metadata = _baseline_metadata(baseline_path)
    if metadata is not None:
        payload["baseline_metadata"] = metadata
    return payload


def _validate_contract(payload: dict[str, Any]) -> None:
    required_fields = ["phase", "generated_at", "source", "status", "metric", "value", "target", "operator", "pass", "context", "gates"]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Self-test: missing required field '{field}'.")
    if payload["phase"] != PHASE_ID:
        raise ValueError(f"Self-test: phase must be '{PHASE_ID}'.")
    if payload["source"] != SOURCE:
        raise ValueError(f"Self-test: source must be '{SOURCE}'.")
    if payload["status"] not in {"pass", "fail"}:
        raise ValueError("Self-test: status must be pass/fail.")
    if isinstance(payload["value"], bool) or not isinstance(payload["value"], (int, float)):
        raise ValueError("Self-test: value must be numeric.")
    if isinstance(payload["target"], bool) or not isinstance(payload["target"], (int, float)):
        raise ValueError("Self-test: target must be numeric.")
    if payload["operator"] not in ALLOWED_OPERATORS:
        raise ValueError("Self-test: operator must be gte/lte/eq.")
    if not isinstance(payload["pass"], bool):
        raise ValueError("Self-test: pass must be boolean.")
    if not isinstance(payload["context"], dict):
        raise ValueError("Self-test: context must be object.")
    gates = payload["gates"]
    if not isinstance(gates, list) or len(gates) < 1:
        raise ValueError("Self-test: gates must be a non-empty list.")
    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("Self-test: gate entries must be objects.")
        for field in ("id", "source", "metric", "value", "operator", "target", "pass", "artifact"):
            if field not in gate:
                raise ValueError(f"Self-test: gate missing field '{field}'.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Optional baseline manifest path.",
    )
    parser.add_argument("--candidate", type=Path, help="Optional candidate reference path.")
    parser.add_argument("--self-test", action="store_true", help="Validate output contract before exit.")
    parser.add_argument(
        "--gates-file",
        type=Path,
        default=DEFAULT_GATES_FILE,
        help="Path to phase gate definitions.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    evidence_dir = args.output.parent
    try:
        gates = _phase_gates(args.gates_file)
        payload = _build_report(
            gates=gates,
            evidence_dir=evidence_dir,
            baseline_path=args.baseline,
            candidate_path=args.candidate,
        )
        if args.self_test:
            _validate_contract(payload)
    except Exception as exc:
        print(f"Phase 07 gate evaluation failed: {exc}")
        return 1

    text = json.dumps(payload, indent=2, ensure_ascii=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if bool(payload["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())

