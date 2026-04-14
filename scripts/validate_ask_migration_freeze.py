#!/usr/bin/env python3
"""Validate ask-migration freeze governance artifacts and A0 closure evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_CONTRACTS = {f"AQC{i}" for i in range(0, 8)}
EXPECTED_PHASE_IDS = [f"A{i}" for i in range(0, 8)]
ALLOWED_OPERATORS = {"gte", "lte", "eq"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _evaluate(operator: str, value: float, target: float) -> bool:
    if operator == "lte":
        return value <= target
    if operator == "gte":
        return value >= target
    if operator == "eq":
        return value == target
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    migration_root = repo_root / "docs" / "render" / "ask-migration-phases"
    freeze_root = migration_root / "system-freeze"
    contracts_root = freeze_root / "contracts"
    phase_a0_root = migration_root / "phase-a0-contract-freeze-ask-queue"
    phase_a0_evidence_root = phase_a0_root / "evidence"

    errors: list[str] = []

    required_files = [
        migration_root / "README.md",
        freeze_root / "README.md",
        freeze_root / "phase-manifest-v1.json",
        freeze_root / "phase-gates-v1.json",
        contracts_root / "README.md",
        contracts_root / "aqc0-ask-queue-parity-scope-v1.md",
        contracts_root / "aqc1-ask-queue-core-contract-v1.md",
        contracts_root / "aqc2-ask-idempotency-contract-v1.md",
        contracts_root / "aqc3-ask-send-window-contract-v1.md",
        contracts_root / "aqc4-ask-confirmation-risk-contract-v1.md",
        contracts_root / "aqc5-ask-shell-integrity-contract-v1.md",
        contracts_root / "aqc6-ask-recovery-reset-contract-v1.md",
        contracts_root / "aqc7-ask-rollout-gate-contract-v1.md",
        phase_a0_root / "README.md",
        phase_a0_root / "preflight-v1.md",
        phase_a0_root / "ask-queue-contract-v1.md",
        phase_a0_root / "ask-queue-gating-matrix-v1.md",
        phase_a0_root / "ask-queue-risk-baseline-v1.md",
        phase_a0_root / "close-phase-v1.md",
        phase_a0_evidence_root / "README.md",
        phase_a0_evidence_root / "baseline-manifest-v1.json",
        phase_a0_evidence_root / "ask_contract_review_checklist.json",
        phase_a0_evidence_root / "ask_scope_freeze_audit.json",
        phase_a0_evidence_root / "ask_arch_signoff_log.json",
        phase_a0_evidence_root / "phase-a0-gate-report.json",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Missing required file: {path}")

    if errors:
        print("Ask migration freeze validation: FAIL")
        print(f"Errors: {len(errors)}")
        for error in errors:
            print(f"- {error}")
        return 1

    manifest = _load_json(freeze_root / "phase-manifest-v1.json")
    gates = _load_json(freeze_root / "phase-gates-v1.json")

    if str(manifest.get("model") or "").strip() != "execution-to-ask-queue-parity":
        errors.append("Manifest model must be 'execution-to-ask-queue-parity'.")

    manifest_contracts = set(str(item) for item in manifest.get("contracts", []))
    if manifest_contracts != EXPECTED_CONTRACTS:
        errors.append(
            "Manifest contracts mismatch. "
            f"Expected {sorted(EXPECTED_CONTRACTS)}, got {sorted(manifest_contracts)}."
        )

    phase_entries = manifest.get("phases", [])
    if len(phase_entries) != len(EXPECTED_PHASE_IDS):
        errors.append(f"Manifest must define {len(EXPECTED_PHASE_IDS)} phases, found {len(phase_entries)}.")

    phase_map: dict[str, dict[str, Any]] = {}
    for entry in phase_entries:
        pid = str(entry.get("id") or "").strip()
        if not pid:
            errors.append("Manifest phase entry with empty id.")
            continue
        if pid in phase_map:
            errors.append(f"Duplicate phase id in manifest: {pid}")
        phase_map[pid] = entry

    for pid in EXPECTED_PHASE_IDS:
        entry = phase_map.get(pid)
        if entry is None:
            errors.append(f"Missing phase id in manifest: {pid}")
            continue

        readme_rel = str(entry.get("readme") or "").strip()
        if not readme_rel:
            errors.append(f"Phase {pid}: readme path is required.")
        elif not (repo_root / readme_rel).exists():
            errors.append(f"Phase {pid}: readme path does not exist: {readme_rel}")

        gate_entries = gates.get("phases", {}).get(pid)
        if not isinstance(gate_entries, list) or not gate_entries:
            errors.append(f"Phase {pid}: missing gate definitions.")
            continue

        expected_gate_ids = {str(item) for item in entry.get("exit_gates", [])}
        actual_gate_ids = {str(item.get("id") or "") for item in gate_entries}
        if expected_gate_ids != actual_gate_ids:
            errors.append(
                f"Phase {pid}: gate id mismatch. "
                f"Expected {sorted(expected_gate_ids)}, got {sorted(actual_gate_ids)}."
            )

        for gate in gate_entries:
            gid = str(gate.get("id") or "").strip()
            operator = str(gate.get("operator") or "").strip()
            if operator not in ALLOWED_OPERATORS:
                errors.append(f"Phase {pid} gate {gid}: invalid operator '{operator}'.")
            for field in ("metric", "source", "target"):
                if field not in gate:
                    errors.append(f"Phase {pid} gate {gid}: missing field '{field}'.")

    # A0 closure source validation + gate evaluation
    phase_a0_gates = gates.get("phases", {}).get("A0", [])
    gate_by_source = {str(item.get("source") or "").strip(): item for item in phase_a0_gates}
    canonical_artifacts = {
        "ask_contract_review_checklist": phase_a0_evidence_root / "ask_contract_review_checklist.json",
        "ask_scope_freeze_audit": phase_a0_evidence_root / "ask_scope_freeze_audit.json",
        "ask_arch_signoff_log": phase_a0_evidence_root / "ask_arch_signoff_log.json",
    }

    pass_count = 0
    for source, artifact_path in canonical_artifacts.items():
        gate = gate_by_source.get(source)
        if gate is None:
            errors.append(f"A0 missing gate definition for source '{source}'.")
            continue

        payload = _load_json(artifact_path)
        gate_id = str(gate.get("id") or "").strip()
        metric = str(gate.get("metric") or "").strip()
        operator = str(gate.get("operator") or "").strip()
        target = gate.get("target")

        if str(payload.get("phase") or "").strip() != "A0":
            errors.append(f"{artifact_path}: phase must be 'A0'.")
        if str(payload.get("gate_id") or "").strip() != gate_id:
            errors.append(f"{artifact_path}: gate_id must be '{gate_id}'.")
        if str(payload.get("source") or "").strip() != source:
            errors.append(f"{artifact_path}: source must be '{source}'.")
        if str(payload.get("metric") or "").strip() != metric:
            errors.append(f"{artifact_path}: metric must be '{metric}'.")
        if str(payload.get("operator") or "").strip() != operator:
            errors.append(f"{artifact_path}: operator must be '{operator}'.")
        if payload.get("target") != target:
            errors.append(f"{artifact_path}: target must be {target}.")

        evidence_mode = str(payload.get("evidence_mode") or "").strip()
        gate_eligible = payload.get("gate_eligible")
        if evidence_mode != "candidate":
            errors.append(f"{artifact_path}: evidence_mode must be 'candidate'.")
        if gate_eligible is not True:
            errors.append(f"{artifact_path}: gate_eligible must be true.")

        context = payload.get("context")
        if not isinstance(context, dict):
            errors.append(f"{artifact_path}: context object is required.")
            continue
        candidate_path = str(context.get("candidate_path") or "").strip()
        candidate_commit_sha = str(context.get("candidate_commit_sha") or "").strip()
        if not candidate_path:
            errors.append(f"{artifact_path}: context.candidate_path is required.")
        else:
            candidate_abs = repo_root / candidate_path
            if not candidate_abs.exists():
                errors.append(f"{artifact_path}: candidate_path does not exist: {candidate_path}")
        if not candidate_commit_sha:
            errors.append(f"{artifact_path}: context.candidate_commit_sha is required.")

        value = payload.get("value")
        if not _is_number(value):
            errors.append(f"{artifact_path}: value must be numeric.")
            continue
        if not _is_number(target):
            errors.append(f"A0 gate target for source '{source}' must be numeric.")
            continue

        computed_pass = _evaluate(operator, float(value), float(target))
        declared_pass = payload.get("pass")
        if declared_pass is not computed_pass:
            errors.append(
                f"{artifact_path}: pass mismatch (declared={declared_pass}, computed={computed_pass})."
            )
        if computed_pass:
            pass_count += 1

    gate_report = _load_json(phase_a0_evidence_root / "phase-a0-gate-report.json")
    if str(gate_report.get("phase") or "").strip() != "A0":
        errors.append("phase-a0-gate-report.json: phase must be 'A0'.")
    if str(gate_report.get("source") or "").strip() != "ask_phase_gate_report":
        errors.append("phase-a0-gate-report.json: source must be 'ask_phase_gate_report'.")
    if str(gate_report.get("metric") or "").strip() != "phase_a0_gate_pass_count":
        errors.append("phase-a0-gate-report.json: metric must be 'phase_a0_gate_pass_count'.")
    if str(gate_report.get("operator") or "").strip() != "eq":
        errors.append("phase-a0-gate-report.json: operator must be 'eq'.")

    total_gates = len(phase_a0_gates)
    if gate_report.get("target") != total_gates:
        errors.append(f"phase-a0-gate-report.json: target must be {total_gates}.")
    if gate_report.get("value") != pass_count:
        errors.append(f"phase-a0-gate-report.json: value must be {pass_count}.")

    expected_phase_pass = pass_count == total_gates and total_gates > 0
    if bool(gate_report.get("pass")) is not expected_phase_pass:
        errors.append(
            "phase-a0-gate-report.json: pass flag does not match computed phase result."
        )
    expected_status = "pass" if expected_phase_pass else "fail"
    if str(gate_report.get("status") or "").strip() != expected_status:
        errors.append(
            f"phase-a0-gate-report.json: status must be '{expected_status}'."
        )

    close_phase_text = (phase_a0_root / "close-phase-v1.md").read_text(encoding="utf-8")
    if "phase_a0_passed" not in close_phase_text:
        errors.append("close-phase-v1.md must include the handoff marker 'phase_a0_passed'.")

    if errors:
        print("Ask migration freeze validation: FAIL")
        print(f"Errors: {len(errors)}")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Ask migration freeze validation: PASS")
    print(f"Validated phases: {len(EXPECTED_PHASE_IDS)}")
    print(f"Validated contracts: {len(EXPECTED_CONTRACTS)}")
    print(f"A0 pass gates: {pass_count}/{total_gates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
