#!/usr/bin/env python3
"""Generate Phase A7 rollback drill source evidence (AQ7-G3)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_ID = "A7"
SOURCE = "ask_rollback_drill_report"
DEFAULT_OUTPUT = Path(
    "docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_rollback_drill_report.json"
)
DEFAULT_BASELINE = Path(
    "docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/baseline-manifest-v1.json"
)
DEFAULT_GATES_FILE = Path("docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json")
ALLOWED_OPERATORS = {"gte", "lte", "eq"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object.")
    return payload


def _dig(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for token in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _first_number(payload: dict[str, Any], dotted_keys: list[str]) -> float | None:
    for dotted_key in dotted_keys:
        value = _dig(payload, dotted_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _evaluate(operator: str, value: float, target: float) -> bool:
    if operator == "gte":
        return value >= target
    if operator == "lte":
        return value <= target
    if operator == "eq":
        return value == target
    raise ValueError(f"Unsupported operator: {operator}")


def _gate_contract(gates_file: Path) -> dict[str, Any]:
    payload = _load_json(gates_file)
    phases = payload.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("phase-gates JSON missing 'phases' object.")
    phase_gates = phases.get(PHASE_ID)
    if not isinstance(phase_gates, list):
        raise ValueError(f"phase-gates JSON missing phase '{PHASE_ID}'.")
    for gate in phase_gates:
        if not isinstance(gate, dict):
            continue
        if str(gate.get("source") or "").strip() != SOURCE:
            continue
        metric = str(gate.get("metric") or "").strip()
        operator = str(gate.get("operator") or "").strip()
        target = gate.get("target")
        unit = str(gate.get("unit") or "").strip()
        if not metric:
            raise ValueError(f"{SOURCE}: gate definition missing metric.")
        if operator not in ALLOWED_OPERATORS:
            raise ValueError(f"{SOURCE}: invalid operator in gate definition: {operator}")
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            raise ValueError(f"{SOURCE}: gate definition missing numeric target.")
        return {
            "id": str(gate.get("id") or "").strip(),
            "metric": metric,
            "operator": operator,
            "target": float(target),
            "unit": unit,
        }
    raise ValueError(f"phase-gates JSON missing source '{SOURCE}' in phase '{PHASE_ID}'.")


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


def _resolve_evidence_inputs(
    *,
    candidate_path: Path | None,
    allow_synthetic: bool,
    candidate_commit_sha: str | None,
) -> tuple[str, bool, Path | None, str]:
    normalized_sha = str(candidate_commit_sha or "").strip()
    if candidate_path is None:
        if not allow_synthetic:
            raise ValueError(
                "Missing --candidate. Provide candidate evidence or use --allow-synthetic for local dry-run only."
            )
        return ("synthetic", False, None, "synthetic-local")
    if not candidate_path.exists():
        raise ValueError(f"Candidate file not found: {candidate_path}")
    if not normalized_sha:
        raise ValueError(
            "Missing candidate commit SHA. Provide --candidate-commit-sha or set PTM_CANDIDATE_COMMIT_SHA."
        )
    return ("candidate", True, candidate_path, normalized_sha)


def _build_payload(
    *,
    gate: dict[str, Any],
    baseline_path: Path | None,
    candidate_path: Path | None,
    allow_synthetic: bool,
    candidate_commit_sha: str | None,
) -> dict[str, Any]:
    evidence_mode, gate_eligible, resolved_candidate_path, resolved_commit_sha = _resolve_evidence_inputs(
        candidate_path=candidate_path,
        allow_synthetic=allow_synthetic,
        candidate_commit_sha=candidate_commit_sha,
    )

    rollback_failures = 0.0
    rollback_drills_total = 0.0
    rollback_recovery_time_seconds_p95 = 0.0
    rollback_execution_regression_events = 0.0

    if resolved_candidate_path is not None:
        candidate_payload = _load_json(resolved_candidate_path)
        extracted_failures = _first_number(
            candidate_payload,
            [
                "candidate_metrics.ask_rollback_drill_failures",
                "context.ask_rollback_drill_failures",
                "value",
            ],
        )
        if extracted_failures is not None and extracted_failures >= 0:
            rollback_failures = extracted_failures

        extracted_total = _first_number(
            candidate_payload,
            [
                "candidate_metrics.ask_rollback_drills_total",
                "context.ask_rollback_drills_total",
            ],
        )
        if extracted_total is not None and extracted_total >= 0:
            rollback_drills_total = extracted_total

        extracted_p95 = _first_number(
            candidate_payload,
            [
                "candidate_metrics.ask_rollback_recovery_time_seconds_p95",
                "context.ask_rollback_recovery_time_seconds_p95",
            ],
        )
        if extracted_p95 is not None and extracted_p95 >= 0:
            rollback_recovery_time_seconds_p95 = extracted_p95

        extracted_execution_regressions = _first_number(
            candidate_payload,
            [
                "candidate_metrics.ask_rollback_execution_regression_events",
                "context.ask_rollback_execution_regression_events",
            ],
        )
        if extracted_execution_regressions is not None and extracted_execution_regressions >= 0:
            rollback_execution_regression_events = extracted_execution_regressions

    metric_value = round(float(rollback_failures), 3)
    target = float(gate["target"])
    operator = str(gate["operator"])
    passed = _evaluate(operator, metric_value, target)
    payload: dict[str, Any] = {
        "phase": PHASE_ID,
        "gate_id": str(gate["id"]),
        "source": SOURCE,
        "generated_at": _now_iso(),
        "evidence_mode": evidence_mode,
        "gate_eligible": gate_eligible,
        "status": "pass" if passed else "fail",
        "context": {
            "scenario": "ask_phase_a7_rollback_drill_v1",
            "ask_rollback_drill_failures": metric_value,
            "ask_rollback_drills_total": int(rollback_drills_total),
            "ask_rollback_recovery_time_seconds_p95": round(float(rollback_recovery_time_seconds_p95), 3),
            "ask_rollback_execution_regression_events": int(rollback_execution_regression_events),
            "candidate_path": resolved_candidate_path.as_posix() if resolved_candidate_path is not None else None,
            "candidate_commit_sha": resolved_commit_sha,
        },
        "metric": str(gate["metric"]),
        "value": metric_value,
        "operator": operator,
        "target": target,
        "unit": str(gate["unit"]),
        "pass": passed,
    }
    metadata = _baseline_metadata(baseline_path)
    if metadata is not None:
        payload["baseline_metadata"] = metadata
    return payload


def _validate_contract(payload: dict[str, Any]) -> None:
    required_fields = [
        "phase",
        "gate_id",
        "source",
        "generated_at",
        "evidence_mode",
        "gate_eligible",
        "status",
        "context",
        "metric",
        "value",
        "operator",
        "target",
        "unit",
        "pass",
    ]
    for field in required_fields:
        if field not in payload:
            raise ValueError(f"Self-test: missing required field '{field}'.")
    if payload["phase"] != PHASE_ID:
        raise ValueError(f"Self-test: phase must be '{PHASE_ID}'.")
    if payload["source"] != SOURCE:
        raise ValueError(f"Self-test: source must be '{SOURCE}'.")
    if payload["evidence_mode"] not in {"candidate", "synthetic"}:
        raise ValueError("Self-test: evidence_mode must be candidate/synthetic.")
    if not isinstance(payload["gate_eligible"], bool):
        raise ValueError("Self-test: gate_eligible must be boolean.")
    if payload["status"] not in {"pass", "fail"}:
        raise ValueError("Self-test: status must be pass/fail.")
    if not isinstance(payload.get("context"), dict):
        raise ValueError("Self-test: context must be object.")
    if isinstance(payload["value"], bool) or not isinstance(payload["value"], (int, float)):
        raise ValueError("Self-test: value must be numeric.")
    if isinstance(payload["target"], bool) or not isinstance(payload["target"], (int, float)):
        raise ValueError("Self-test: target must be numeric.")
    if payload["operator"] not in ALLOWED_OPERATORS:
        raise ValueError("Self-test: operator must be gte/lte/eq.")
    if not isinstance(payload["pass"], bool):
        raise ValueError("Self-test: pass must be boolean.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help="Optional baseline manifest path.")
    parser.add_argument(
        "--candidate",
        type=Path,
        help="Candidate source JSON path. Required unless --allow-synthetic is set.",
    )
    parser.add_argument(
        "--candidate-commit-sha",
        type=str,
        help="Candidate commit SHA (required with --candidate). Can also come from PTM_CANDIDATE_COMMIT_SHA.",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Allow synthetic fallback evidence for local dry-run only (marks gate_eligible=false).",
    )
    parser.add_argument("--self-test", action="store_true", help="Validate output contract before exit.")
    parser.add_argument("--gates-file", type=Path, default=DEFAULT_GATES_FILE, help="Path to phase gate definitions.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        gate = _gate_contract(args.gates_file)
        payload = _build_payload(
            gate=gate,
            baseline_path=args.baseline,
            candidate_path=args.candidate,
            allow_synthetic=args.allow_synthetic,
            candidate_commit_sha=args.candidate_commit_sha or os.environ.get("PTM_CANDIDATE_COMMIT_SHA"),
        )
        if args.self_test:
            _validate_contract(payload)
    except Exception as exc:
        print(f"Phase A7 rollback drill source evidence generation failed: {exc}")
        return 1

    text = json.dumps(payload, indent=2, ensure_ascii=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
