#!/usr/bin/env python3
"""Generate Phase 14.7 resilience hardening evidence report.

This script aggregates three scenario inputs (lagged subscriber, replay-edge reconnect,
long session volume) and emits a gate-style JSON artifact for roadmap phase 14.7.

Expected candidate schema (flexible dotted-key lookup is supported):
{
  "candidate_metrics": {
    "lagged_subscriber_reconnect_rate": 0.12,
    "replay_edge_mismatch_reload_rate": 0.4,
    "long_session_live_items_exceeds_cap_events": 0,
    "transient_reconnect_unnecessary_forced_reload": 0
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

PHASE_ID = "14.7"
SOURCE = "resilience_long_session_hardening"
DEFAULT_OUTPUT = Path(
    "docs/render/phases/phase-14-goose-like-streaming-smoothness/evidence/phase14_7_resilience_hardening_report.json"
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

    # Conservative synthetic defaults (pass)
    lagged_subscriber_reconnect_rate = 0.15
    replay_edge_mismatch_reload_rate = 0.8
    long_session_live_items_exceeds_cap_events = 0.0
    transient_reconnect_unnecessary_forced_reload = 0.0

    if resolved_candidate is not None:
        payload = _load_json(resolved_candidate)
        lagged_subscriber_reconnect_rate = _first_number(
            payload,
            [
                "candidate_metrics.lagged_subscriber_reconnect_rate",
                "context.lagged_subscriber_reconnect_rate",
                "lagged_subscriber_reconnect_rate",
            ],
            lagged_subscriber_reconnect_rate,
        )
        replay_edge_mismatch_reload_rate = _first_number(
            payload,
            [
                "candidate_metrics.replay_edge_mismatch_reload_rate",
                "candidate_metrics.mismatch_reload_rate",
                "context.replay_edge_mismatch_reload_rate",
                "replay_edge_mismatch_reload_rate",
            ],
            replay_edge_mismatch_reload_rate,
        )
        long_session_live_items_exceeds_cap_events = _first_number(
            payload,
            [
                "candidate_metrics.long_session_live_items_exceeds_cap_events",
                "candidate_metrics.live_items_exceeds_scrollback_cap_events",
                "context.long_session_live_items_exceeds_cap_events",
                "long_session_live_items_exceeds_cap_events",
            ],
            long_session_live_items_exceeds_cap_events,
        )
        transient_reconnect_unnecessary_forced_reload = _first_number(
            payload,
            [
                "candidate_metrics.transient_reconnect_unnecessary_forced_reload",
                "candidate_metrics.transient_reconnect_forced_reload_count",
                "context.transient_reconnect_unnecessary_forced_reload",
                "transient_reconnect_unnecessary_forced_reload",
            ],
            transient_reconnect_unnecessary_forced_reload,
        )

    thresholds = {
        "lagged_subscriber_reconnect_rate_lte": 0.35,
        "replay_edge_mismatch_reload_rate_lte": 1.5,
        "long_session_live_items_exceeds_cap_events_eq": 0.0,
        "transient_reconnect_unnecessary_forced_reload_eq": 0.0,
    }

    checks = {
        "lagged_subscriber_reconnect_rate": lagged_subscriber_reconnect_rate <= thresholds["lagged_subscriber_reconnect_rate_lte"],
        "replay_edge_mismatch_reload_rate": replay_edge_mismatch_reload_rate <= thresholds["replay_edge_mismatch_reload_rate_lte"],
        "long_session_live_items_exceeds_cap_events": long_session_live_items_exceeds_cap_events
        == thresholds["long_session_live_items_exceeds_cap_events_eq"],
        "transient_reconnect_unnecessary_forced_reload": transient_reconnect_unnecessary_forced_reload
        == thresholds["transient_reconnect_unnecessary_forced_reload_eq"],
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
                "lagged_subscriber_reconnect_rate": round(float(lagged_subscriber_reconnect_rate), 4),
                "replay_edge_mismatch_reload_rate": round(float(replay_edge_mismatch_reload_rate), 4),
                "long_session_live_items_exceeds_cap_events": int(long_session_live_items_exceeds_cap_events),
                "transient_reconnect_unnecessary_forced_reload": int(
                    transient_reconnect_unnecessary_forced_reload
                ),
            },
            "checks": checks,
            "notes": [
                "Phase 14.7 aggregates lagged-subscriber, replay-edge, and long-session resilience checks.",
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
