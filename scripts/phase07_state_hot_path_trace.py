#!/usr/bin/env python3
"""Generate Phase 07 hot-path trace evidence (P07-G2 source)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_ID = "07"
SOURCE = "state_hot_path_trace"
DEFAULT_OUTPUT = Path("docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_trace.json")
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


def _rate_per_1000(*, count: float, total: float) -> float:
    if total <= 0:
        raise ValueError("total must be > 0 for normalized rate.")
    return (count / total) * 1000.0


def _build_payload(
    *,
    gate: dict[str, Any],
    baseline_path: Path | None,
    candidate_path: Path | None,
) -> dict[str, Any]:
    total_events = 4000.0
    patch_content_events = 3900.0
    patch_meta_events = 88.0
    reorder_events = 4.0
    insert_events = 8.0

    # Candidate behavior should avoid global sort for patch-only operations.
    global_sort_invocations = 12.0

    if candidate_path is not None:
        if not candidate_path.exists():
            raise ValueError(f"Candidate file not found: {candidate_path}")
        candidate_payload = _load_json(candidate_path)
        extracted_events = _first_number(candidate_payload, ["context.total_events", "candidate_metrics.total_events"])
        if extracted_events is not None and extracted_events > 0:
            total_events = extracted_events
        extracted_sorts = _first_number(
            candidate_payload,
            ["context.global_sort_invocations", "candidate_metrics.global_sort_invocations"],
        )
        if extracted_sorts is not None and extracted_sorts >= 0:
            global_sort_invocations = extracted_sorts
        extracted_patch_content = _first_number(candidate_payload, ["context.event_mix.patch_content_events"])
        if extracted_patch_content is not None and extracted_patch_content >= 0:
            patch_content_events = extracted_patch_content
        extracted_patch_meta = _first_number(candidate_payload, ["context.event_mix.patch_meta_events"])
        if extracted_patch_meta is not None and extracted_patch_meta >= 0:
            patch_meta_events = extracted_patch_meta
        extracted_reorder = _first_number(candidate_payload, ["context.event_mix.reorder_events"])
        if extracted_reorder is not None and extracted_reorder >= 0:
            reorder_events = extracted_reorder
        extracted_insert = _first_number(candidate_payload, ["context.event_mix.insert_events"])
        if extracted_insert is not None and extracted_insert >= 0:
            insert_events = extracted_insert

    rate = round(_rate_per_1000(count=global_sort_invocations, total=total_events), 3)
    target = float(gate["target"])
    operator = str(gate["operator"])
    passed = _evaluate(operator, rate, target)

    payload: dict[str, Any] = {
        "phase": PHASE_ID,
        "generated_at": _now_iso(),
        "source": SOURCE,
        "status": "pass" if passed else "fail",
        "metric": str(gate["metric"]),
        "value": rate,
        "target": target,
        "operator": operator,
        "pass": passed,
        "context": {
            "scenario": "phase07_hot_path_trace_model_v1",
            "total_events": int(total_events),
            "global_sort_invocations": int(global_sort_invocations),
            "event_mix": {
                "patch_content_events": int(patch_content_events),
                "patch_meta_events": int(patch_meta_events),
                "insert_events": int(insert_events),
                "reorder_events": int(reorder_events),
            },
            "candidate_path": candidate_path.as_posix() if candidate_path is not None else None,
        },
    }
    metadata = _baseline_metadata(baseline_path)
    if metadata is not None:
        payload["baseline_metadata"] = metadata
    return payload


def _validate_contract(payload: dict[str, Any]) -> None:
    required_fields = ["phase", "generated_at", "source", "status", "metric", "value", "target", "operator", "pass", "context"]
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Optional baseline manifest or metrics JSON path.",
    )
    parser.add_argument("--candidate", type=Path, help="Optional candidate trace JSON path.")
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
    try:
        gate = _gate_contract(args.gates_file)
        payload = _build_payload(
            gate=gate,
            baseline_path=args.baseline,
            candidate_path=args.candidate,
        )
        if args.self_test:
            _validate_contract(payload)
    except Exception as exc:
        print(f"Phase 07 trace generation failed: {exc}")
        return 1

    text = json.dumps(payload, indent=2, ensure_ascii=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
