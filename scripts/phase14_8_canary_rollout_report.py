#!/usr/bin/env python3
"""Generate Phase 14.8 canary rollout + rollback drill gate report.

Candidate schema is flexible; dotted-key lookup is used.
Expected candidate metrics (preferred):
{
  "candidate_metrics": {
    "ask_inter_update_gap_p95_ms": 78,
    "execution_inter_update_gap_p95_ms": 118,
    "ask_reconnect_per_session": 0.24,
    "execution_reconnect_per_session": 0.31,
    "mismatch_reload_rate": 0.9,
    "rollback_drill_validated": true
  },
  "baseline_metrics": {
    "ask_inter_update_gap_p95_ms": 90,
    "execution_inter_update_gap_p95_ms": 130
  }
}
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE_ID = "14.8"
SOURCE = "canary_rollout_and_rollback_drills"
DEFAULT_OUTPUT = Path(
    "docs/render/phases/phase-14-goose-like-streaming-smoothness/evidence/phase14_8_canary_rollout_report.json"
)


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


def _first_number(payload: dict[str, Any], dotted_keys: list[str], fallback: float) -> float:
    for dotted_key in dotted_keys:
        value = _dig(payload, dotted_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return fallback


def _first_bool(payload: dict[str, Any], dotted_keys: list[str], fallback: bool) -> bool:
    for dotted_key in dotted_keys:
        value = _dig(payload, dotted_key)
        if isinstance(value, bool):
            return value
    return fallback


def _resolve_candidate_mode(
    *,
    candidate: Path | None,
    allow_synthetic: bool,
    candidate_commit_sha: str | None,
) -> tuple[str, bool, Path | None, str]:
    commit_sha = str(candidate_commit_sha or "").strip()
    if candidate is None:
        if not allow_synthetic:
            raise ValueError(
                "Missing --candidate. Provide candidate metrics JSON or use --allow-synthetic for local dry-run only."
            )
        return ("synthetic", False, None, "synthetic-local")
    if not candidate.exists():
        raise ValueError(f"Candidate file not found: {candidate}")
    if not commit_sha:
        raise ValueError(
            "Missing candidate commit SHA. Provide --candidate-commit-sha or set PTM_CANDIDATE_COMMIT_SHA."
        )
    return ("candidate", True, candidate, commit_sha)


def _build_payload(
    *,
    candidate: Path | None,
    allow_synthetic: bool,
    candidate_commit_sha: str | None,
) -> dict[str, Any]:
    evidence_mode, gate_eligible, resolved_candidate, resolved_commit_sha = _resolve_candidate_mode(
        candidate=candidate,
        allow_synthetic=allow_synthetic,
        candidate_commit_sha=candidate_commit_sha,
    )

    # Synthetic defaults (pass)
    ask_gap_p95 = 80.0
    exec_gap_p95 = 120.0
    ask_baseline_gap_p95 = 90.0
    exec_baseline_gap_p95 = 130.0
    ask_reconnect_per_session = 0.25
    execution_reconnect_per_session = 0.32
    mismatch_reload_rate = 1.0
    rollback_drill_validated = True

    if resolved_candidate is not None:
        payload = _load_json(resolved_candidate)
        ask_gap_p95 = _first_number(
            payload,
            [
                "candidate_metrics.ask_inter_update_gap_p95_ms",
                "ask_inter_update_gap_p95_ms",
            ],
            ask_gap_p95,
        )
        exec_gap_p95 = _first_number(
            payload,
            [
                "candidate_metrics.execution_inter_update_gap_p95_ms",
                "execution_inter_update_gap_p95_ms",
            ],
            exec_gap_p95,
        )
        ask_baseline_gap_p95 = _first_number(
            payload,
            [
                "baseline_metrics.ask_inter_update_gap_p95_ms",
                "baseline.ask_inter_update_gap_p95_ms",
            ],
            ask_baseline_gap_p95,
        )
        exec_baseline_gap_p95 = _first_number(
            payload,
            [
                "baseline_metrics.execution_inter_update_gap_p95_ms",
                "baseline.execution_inter_update_gap_p95_ms",
            ],
            exec_baseline_gap_p95,
        )
        ask_reconnect_per_session = _first_number(
            payload,
            [
                "candidate_metrics.ask_reconnect_per_session",
                "ask_reconnect_per_session",
            ],
            ask_reconnect_per_session,
        )
        execution_reconnect_per_session = _first_number(
            payload,
            [
                "candidate_metrics.execution_reconnect_per_session",
                "execution_reconnect_per_session",
            ],
            execution_reconnect_per_session,
        )
        mismatch_reload_rate = _first_number(
            payload,
            [
                "candidate_metrics.mismatch_reload_rate",
                "mismatch_reload_rate",
            ],
            mismatch_reload_rate,
        )
        rollback_drill_validated = _first_bool(
            payload,
            [
                "candidate_metrics.rollback_drill_validated",
                "rollback_drill_validated",
            ],
            rollback_drill_validated,
        )

    ask_regression_ratio = ask_gap_p95 / max(ask_baseline_gap_p95, 1.0)
    exec_regression_ratio = exec_gap_p95 / max(exec_baseline_gap_p95, 1.0)

    thresholds = {
        "inter_update_gap_regression_ratio_lte": 1.10,
        "ask_reconnect_per_session_lte": 0.50,
        "execution_reconnect_per_session_lte": 0.60,
        "mismatch_reload_rate_lte": 1.50,
        "rollback_drill_validated_eq": True,
    }

    checks = {
        "ask_inter_update_gap_regression": ask_regression_ratio <= thresholds["inter_update_gap_regression_ratio_lte"],
        "execution_inter_update_gap_regression": exec_regression_ratio <= thresholds[
            "inter_update_gap_regression_ratio_lte"
        ],
        "ask_reconnect_per_session": ask_reconnect_per_session <= thresholds["ask_reconnect_per_session_lte"],
        "execution_reconnect_per_session": execution_reconnect_per_session
        <= thresholds["execution_reconnect_per_session_lte"],
        "mismatch_reload_rate": mismatch_reload_rate <= thresholds["mismatch_reload_rate_lte"],
        "rollback_drill_validated": rollback_drill_validated == thresholds["rollback_drill_validated_eq"],
    }

    passed = all(checks.values())

    return {
        "phase": PHASE_ID,
        "generated_at": _now_iso(),
        "source": SOURCE,
        "evidence_mode": evidence_mode,
        "gate_eligible": gate_eligible,
        "status": "pass" if passed else "fail",
        "pass": passed,
        "context": {
            "candidate_path": resolved_candidate.as_posix() if resolved_candidate is not None else None,
            "candidate_commit_sha": resolved_commit_sha,
            "thresholds": thresholds,
            "metrics": {
                "ask_inter_update_gap_p95_ms": round(ask_gap_p95, 2),
                "execution_inter_update_gap_p95_ms": round(exec_gap_p95, 2),
                "ask_baseline_inter_update_gap_p95_ms": round(ask_baseline_gap_p95, 2),
                "execution_baseline_inter_update_gap_p95_ms": round(exec_baseline_gap_p95, 2),
                "ask_reconnect_per_session": round(ask_reconnect_per_session, 4),
                "execution_reconnect_per_session": round(execution_reconnect_per_session, 4),
                "mismatch_reload_rate": round(mismatch_reload_rate, 4),
                "rollback_drill_validated": rollback_drill_validated,
                "ask_gap_regression_ratio": round(ask_regression_ratio, 4),
                "execution_gap_regression_ratio": round(exec_regression_ratio, 4),
            },
            "checks": checks,
            "notes": [
                "Phase 14.8 gates canary rollout progression and rollback drill completion.",
                "Synthetic mode is non-gate-eligible and for local dry-run only.",
            ],
        },
    }


def _validate_contract(payload: dict[str, Any]) -> None:
    required = ["phase", "generated_at", "source", "evidence_mode", "gate_eligible", "status", "pass", "context"]
    for field in required:
        if field not in payload:
            raise ValueError(f"Self-test: missing required field '{field}'.")

    if payload["phase"] != PHASE_ID:
        raise ValueError(f"Self-test: phase must be '{PHASE_ID}'.")
    if payload["source"] != SOURCE:
        raise ValueError(f"Self-test: source must be '{SOURCE}'.")
    if payload["evidence_mode"] not in {"candidate", "synthetic"}:
        raise ValueError("Self-test: evidence_mode must be candidate/synthetic.")
    if payload["status"] not in {"pass", "fail"}:
        raise ValueError("Self-test: status must be pass/fail.")
    if not isinstance(payload["gate_eligible"], bool):
        raise ValueError("Self-test: gate_eligible must be boolean.")
    if not isinstance(payload["pass"], bool):
        raise ValueError("Self-test: pass must be boolean.")
    if not isinstance(payload["context"], dict):
        raise ValueError("Self-test: context must be object.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=None, help="Candidate metrics JSON path.")
    parser.add_argument(
        "--candidate-commit-sha",
        default=os.getenv("PTM_CANDIDATE_COMMIT_SHA", ""),
        help="Candidate commit SHA (required when --candidate is provided).",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Allow synthetic local fallback when --candidate is missing.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT.as_posix()}).",
    )
    parser.add_argument("--self-test", action="store_true", help="Validate output contract before writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = _build_payload(
        candidate=args.candidate,
        allow_synthetic=args.allow_synthetic,
        candidate_commit_sha=args.candidate_commit_sha,
    )

    if args.self_test:
        _validate_contract(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
