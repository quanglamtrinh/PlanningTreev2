#!/usr/bin/env python3
"""Evaluate Phase 12 gate pass/fail from source evidence JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_ID = "12"
SOURCE = "phase12_gate_report"
DEFAULT_OUTPUT = Path(
    "docs/render/phases/phase-12-data-volume-and-heavy-content-ux/evidence/phase12-gate-report.json"
)
DEFAULT_BASELINE = Path(
    "docs/render/phases/phase-12-data-volume-and-heavy-content-ux/evidence/baseline-manifest-v1.json"
)
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
            raise ValueError("phase-gates contains invalid gate record for phase 12.")
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

    required_sources = {
        "long_session_volume_tests",
        "heavy_row_classification_suite",
        "preview_to_full_navigation_tests",
    }
    actual_sources = {str(g["source"]) for g in resolved}
    missing = sorted(required_sources - actual_sources)
    if missing:
        raise ValueError(f"phase-gates missing required phase 12 sources: {', '.join(missing)}")
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


def _load_source_artifact(*, artifact_path: Path, gate: dict[str, Any]) -> dict[str, Any]:
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
    status = str(payload.get("status") or "").strip()
    if status not in {"pass", "fail"}:
        raise ValueError(f"{artifact_path.as_posix()}: missing/invalid status field.")
    evidence_mode = str(payload.get("evidence_mode") or "").strip()
    gate_eligible = payload.get("gate_eligible")
    context = payload.get("context")
    if not isinstance(context, dict):
        raise ValueError(f"{artifact_path.as_posix()}: missing object field 'context'.")
    candidate_path = context.get("candidate_path")
    candidate_commit_sha = context.get("candidate_commit_sha")

    eligibility_issues: list[str] = []
    if evidence_mode not in {"candidate", "synthetic"}:
        eligibility_issues.append("invalid evidence_mode (expected candidate|synthetic)")
    if not isinstance(gate_eligible, bool):
        eligibility_issues.append("gate_eligible must be boolean")
    if evidence_mode == "candidate":
        if gate_eligible is not True:
            eligibility_issues.append("candidate evidence must set gate_eligible=true")
        if not isinstance(candidate_path, str) or not candidate_path.strip():
            eligibility_issues.append("candidate evidence requires non-empty context.candidate_path")
        if not isinstance(candidate_commit_sha, str) or not candidate_commit_sha.strip():
            eligibility_issues.append("candidate evidence requires non-empty context.candidate_commit_sha")
    elif evidence_mode == "synthetic":
        if gate_eligible is not False:
            eligibility_issues.append("synthetic evidence must set gate_eligible=false")

    return {
        "value": float(value),
        "status": status,
        "evidence_mode": evidence_mode,
        "gate_eligible": bool(gate_eligible) if isinstance(gate_eligible, bool) else False,
        "candidate_path": candidate_path,
        "candidate_commit_sha": candidate_commit_sha,
        "eligibility_issues": eligibility_issues,
    }


def _build_report(
    *,
    gates: list[dict[str, Any]],
    evidence_dir: Path,
    baseline_path: Path | None,
    candidate_path: Path | None,
) -> dict[str, Any]:
    gate_results: list[dict[str, Any]] = []
    pass_count = 0
    eligibility_fail_count = 0
    for gate in gates:
        artifact_path = evidence_dir / f"{gate['source']}.json"
        source_artifact = _load_source_artifact(artifact_path=artifact_path, gate=gate)
        value = float(source_artifact["value"])
        metric_passed = _evaluate(str(gate["operator"]), value, float(gate["target"]))
        eligible = (
            source_artifact["evidence_mode"] == "candidate"
            and source_artifact["gate_eligible"] is True
            and len(source_artifact["eligibility_issues"]) == 0
        )
        passed = metric_passed and eligible and source_artifact["status"] == "pass"
        if passed:
            pass_count += 1
        if not eligible:
            eligibility_fail_count += 1
        gate_results.append(
            {
                "id": str(gate["id"]),
                "source": str(gate["source"]),
                "metric": str(gate["metric"]),
                "value": value,
                "operator": str(gate["operator"]),
                "target": float(gate["target"]),
                "pass": passed,
                "metric_pass": metric_passed,
                "artifact_status": source_artifact["status"],
                "evidence_mode": source_artifact["evidence_mode"],
                "gate_eligible": source_artifact["gate_eligible"],
                "candidate_path": source_artifact["candidate_path"],
                "candidate_commit_sha": source_artifact["candidate_commit_sha"],
                "eligibility_issues": source_artifact["eligibility_issues"],
                "artifact": artifact_path.as_posix(),
            }
        )

    all_pass = pass_count == len(gates)
    payload: dict[str, Any] = {
        "phase": PHASE_ID,
        "generated_at": _now_iso(),
        "source": SOURCE,
        "status": "pass" if all_pass else "fail",
        "metric": "phase12_gate_pass_count",
        "value": float(pass_count),
        "target": float(len(gates)),
        "operator": "eq",
        "pass": all_pass,
        "context": {
            "evidence_dir": evidence_dir.as_posix(),
            "candidate_path": candidate_path.as_posix() if candidate_path is not None else None,
            "gate_count": len(gates),
            "eligibility_fail_count": eligibility_fail_count,
        },
        "summary": {
            "all_pass": all_pass,
            "pass_count": pass_count,
            "total_gates": len(gates),
            "eligibility_fail_count": eligibility_fail_count,
        },
        "gates": gate_results,
    }
    metadata = _baseline_metadata(baseline_path)
    if metadata is not None:
        payload["baseline_metadata"] = metadata
    return payload


def _validate_contract(payload: dict[str, Any]) -> None:
    required_fields = [
        "phase",
        "generated_at",
        "source",
        "status",
        "metric",
        "value",
        "target",
        "operator",
        "pass",
        "context",
        "summary",
        "gates",
    ]
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
    summary = payload["summary"]
    if not isinstance(summary, dict):
        raise ValueError("Self-test: summary must be object.")
    gates = payload["gates"]
    if not isinstance(gates, list) or len(gates) < 1:
        raise ValueError("Self-test: gates must be a non-empty list.")


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
        print(f"Phase 12 gate evaluation failed: {exc}")
        return 1

    text = json.dumps(payload, indent=2, ensure_ascii=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if bool(payload["summary"]["all_pass"]) else 2


if __name__ == "__main__":
    sys.exit(main())
