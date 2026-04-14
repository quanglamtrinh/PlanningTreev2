#!/usr/bin/env python3
"""Validate render system-freeze governance artifacts and phase alignment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_PHASE_IDS = [f"{i:02d}" for i in range(1, 14)]
EXPECTED_CONTRACTS = {"C1", "C2", "C3", "C4", "C5", "C6"}
ALLOWED_OPERATORS = {"gte", "lte", "eq"}
ENTRY_CRITERIA_FILE_RULES = {
    "broker_backpressure_policy_frozen": Path(
        "docs/render/phases/phase-05-persistence-broker-efficiency/broker-backpressure-policy-v1.md"
    ),
    "frontend_batching_policy_frozen": Path(
        "docs/render/phases/phase-06-frame-batching-fast-append/frontend-batching-policy-v1.md"
    ),
    "normalized_state_shape_frozen": Path(
        "docs/render/phases/phase-07-state-shape-hot-path/normalized-state-shape-v1.md"
    ),
    "row_cache_invalidation_policy_frozen": Path(
        "docs/render/phases/phase-09-row-isolation-cache/row-cache-invalidation-policy-v1.md"
    ),
    "list_anchor_invariants_frozen": Path(
        "docs/render/phases/phase-10-progressive-virtualized-rendering/list-anchor-invariants-v1.md"
    ),
    "worker_result_versioning_policy_frozen": Path(
        "docs/render/phases/phase-11-heavy-compute-off-main-thread/worker-result-versioning-policy-v1.md"
    ),
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all(text: str, required_fragments: list[str]) -> list[str]:
    missing: list[str] = []
    for fragment in required_fragments:
        if fragment not in text:
            missing.append(fragment)
    return missing


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate_fixture_against_schema(payload: Any, schema: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["Fixture payload must be a JSON object."]

    errors: list[str] = []
    required_fields = [str(name) for name in schema.get("required", [])]
    properties = schema.get("properties", {})

    for field in required_fields:
        if field not in payload:
            errors.append(f"Missing required field: {field}")

    for field, rules in properties.items():
        if field not in payload or not isinstance(rules, dict):
            continue

        value = payload[field]
        expected_types_raw = rules.get("type")
        expected_types: list[str]
        if isinstance(expected_types_raw, list):
            expected_types = [str(item) for item in expected_types_raw]
        elif isinstance(expected_types_raw, str):
            expected_types = [expected_types_raw]
        else:
            expected_types = []

        if expected_types and not any(_matches_type(value, expected) for expected in expected_types):
            errors.append(f"Field {field} failed type check. Expected {expected_types}, got {type(value).__name__}.")
            continue

        if value is None:
            continue

        enum_values = rules.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            errors.append(f"Field {field} value {value!r} is not in enum {enum_values}.")

        min_length = rules.get("minLength")
        if isinstance(min_length, int) and isinstance(value, str) and len(value) < min_length:
            errors.append(f"Field {field} violates minLength={min_length}.")

        minimum = rules.get("minimum")
        if isinstance(minimum, int) and isinstance(value, int) and not isinstance(value, bool) and value < minimum:
            errors.append(f"Field {field} violates minimum={minimum}.")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    freeze_root = repo_root / "docs" / "render" / "system-freeze"
    phases_root = repo_root / "docs" / "render" / "phases"

    errors: list[str] = []
    warnings: list[str] = []

    required_files = [
        repo_root / "docs" / "render" / "decision-pack-v1.md",
        freeze_root / "README.md",
        freeze_root / "phase-manifest-v1.json",
        freeze_root / "phase-gates-v1.json",
        freeze_root / "phase-1-preflight-checklist-v1.md",
        freeze_root / "contracts" / "README.md",
        freeze_root / "contracts" / "c1-event-stream-contract-v1.md",
        freeze_root / "contracts" / "c1-event-stream-envelope-v1.schema.json",
        freeze_root / "contracts" / "c1-event-stream-control-envelope-v1.schema.json",
        freeze_root / "contracts" / "c1-event-stream-bridge-policy-v1.md",
        freeze_root / "contracts" / "fixtures" / "c1-business-valid-v1.json",
        freeze_root / "contracts" / "fixtures" / "c1-business-invalid-missing-event-id-v1.json",
        freeze_root / "contracts" / "fixtures" / "c1-control-valid-v1.json",
        freeze_root / "contracts" / "fixtures" / "c1-control-invalid-missing-thread-id-v1.json",
        freeze_root / "contracts" / "c2-replay-resync-contract-v1.md",
        freeze_root / "contracts" / "c3-lifecycle-gating-contract-v1.md",
        freeze_root / "contracts" / "c4-durability-contract-v1.md",
        freeze_root / "contracts" / "c4-mini-journal-spec-v1.md",
        freeze_root / "contracts" / "c5-frontend-state-contract-v1.md",
        freeze_root / "contracts" / "c6-queue-contract-v1.md",
        phases_root / "README.md",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Missing required file: {path}")

    if errors:
        print("Render freeze validation failed.")
        for err in errors:
            print(f"- {err}")
        return 1

    manifest = _load_json(freeze_root / "phase-manifest-v1.json")
    gates = _load_json(freeze_root / "phase-gates-v1.json")
    decision_pack_text = (repo_root / "docs" / "render" / "decision-pack-v1.md").read_text(
        encoding="utf-8"
    )
    phase_index_text = (phases_root / "README.md").read_text(encoding="utf-8")

    if manifest.get("model") != "goose-first-hybrid":
        errors.append("Manifest model must be 'goose-first-hybrid'.")

    business_schema = _load_json(freeze_root / "contracts" / "c1-event-stream-envelope-v1.schema.json")
    control_schema = _load_json(freeze_root / "contracts" / "c1-event-stream-control-envelope-v1.schema.json")
    fixture_expectations = [
        ("c1-business-valid-v1.json", business_schema, True),
        ("c1-business-invalid-missing-event-id-v1.json", business_schema, False),
        ("c1-control-valid-v1.json", control_schema, True),
        ("c1-control-invalid-missing-thread-id-v1.json", control_schema, False),
    ]
    fixture_root = freeze_root / "contracts" / "fixtures"
    for fixture_name, schema, should_pass in fixture_expectations:
        payload = _load_json(fixture_root / fixture_name)
        fixture_errors = _validate_fixture_against_schema(payload, schema)
        passed = not fixture_errors
        if should_pass and not passed:
            errors.append(
                f"C1 fixture {fixture_name} expected pass but failed: {'; '.join(fixture_errors)}"
            )
        if not should_pass and passed:
            errors.append(f"C1 fixture {fixture_name} expected fail but passed.")

    manifest_contracts = set(manifest.get("contracts", []))
    if manifest_contracts != EXPECTED_CONTRACTS:
        errors.append(
            f"Manifest contracts mismatch. Expected {sorted(EXPECTED_CONTRACTS)}, got {sorted(manifest_contracts)}."
        )

    phase_entries = manifest.get("phases", [])
    if len(phase_entries) != 13:
        errors.append(f"Manifest must define 13 phases, found {len(phase_entries)}.")

    phase_by_id: dict[str, dict[str, Any]] = {}
    for entry in phase_entries:
        pid = str(entry.get("id", ""))
        if pid in phase_by_id:
            errors.append(f"Duplicate phase id in manifest: {pid}")
        phase_by_id[pid] = entry

    for pid in EXPECTED_PHASE_IDS:
        if pid not in phase_by_id:
            errors.append(f"Missing phase id in manifest: {pid}")

    phase_gates = gates.get("phases", {})
    for pid in EXPECTED_PHASE_IDS:
        entry = phase_by_id.get(pid)
        if not entry:
            continue

        readme_rel = entry.get("readme")
        readme_path = repo_root / str(readme_rel)
        if not readme_path.exists():
            errors.append(f"Phase {pid}: missing README path {readme_rel}")
            continue

        entry_criteria = [str(item) for item in entry.get("entry_criteria", [])]
        for criterion in entry_criteria:
            required_rel_path = ENTRY_CRITERIA_FILE_RULES.get(criterion)
            if required_rel_path is None:
                continue
            required_path = repo_root / required_rel_path
            if not required_path.exists():
                errors.append(
                    f"Phase {pid}: missing required artifact for entry criterion '{criterion}': {required_rel_path}"
                )

        text = readme_path.read_text(encoding="utf-8")
        missing_headers = _contains_all(
            text,
            [
                "## Decision Pack Alignment",
                "Decision source: `docs/render/decision-pack-v1.md`.",
                "Contract focus:",
                "Must-hold decisions:",
            ],
        )
        for fragment in missing_headers:
            errors.append(f"Phase {pid}: missing fragment in README: {fragment}")

        contract_ids = list(entry.get("contracts_primary", [])) + list(entry.get("contracts_secondary", []))
        for cid in contract_ids:
            if f"`{cid}`" not in text:
                errors.append(f"Phase {pid}: contract {cid} not referenced in README.")

        if pid == "04" and "c4-mini-journal-spec-v1.md" not in text:
            errors.append("Phase 04: missing reference to c4-mini-journal-spec-v1.md in README.")
        if pid == "07" and "normalized-state-shape-v1.md" not in text:
            errors.append("Phase 07: missing reference to normalized-state-shape-v1.md in README.")
        if pid == "09" and "row-cache-invalidation-policy-v1.md" not in text:
            errors.append("Phase 09: missing reference to row-cache-invalidation-policy-v1.md in README.")
        if pid == "11" and "worker-result-versioning-policy-v1.md" not in text:
            errors.append("Phase 11: missing reference to worker-result-versioning-policy-v1.md in README.")

        link_fragment = f"./{entry.get('slug')}/README.md"
        if link_fragment not in phase_index_text:
            errors.append(f"Phase index missing link for phase {pid}: {link_fragment}")

        subphase_readme = readme_path.parent / "subphases" / "README.md"
        if not subphase_readme.exists():
            errors.append(f"Phase {pid}: missing subphase README.")
        else:
            sub_text = subphase_readme.read_text(encoding="utf-8")
            required_sub = _contains_all(
                sub_text,
                [
                    "## Required Alignment",
                    "docs/render/decision-pack-v1.md",
                    "Do not introduce behavior that violates parent contract focus",
                ],
            )
            for fragment in required_sub:
                errors.append(f"Phase {pid}: subphase README missing fragment: {fragment}")

        expected_gate_ids = set(entry.get("exit_gates", []))
        actual_phase_gates = phase_gates.get(pid)
        if actual_phase_gates is None:
            errors.append(f"Phase {pid}: missing gate entries in phase-gates-v1.json.")
            continue

        actual_gate_ids = {str(g.get("id")) for g in actual_phase_gates}
        if expected_gate_ids != actual_gate_ids:
            errors.append(
                f"Phase {pid}: gate IDs mismatch. Expected {sorted(expected_gate_ids)}, got {sorted(actual_gate_ids)}."
            )

        if len(actual_phase_gates) < 2:
            errors.append(f"Phase {pid}: must define at least 2 gates.")

        for gate in actual_phase_gates:
            gid = str(gate.get("id", ""))
            missing_gate_fields = [
                field
                for field in ["id", "metric", "operator", "target", "source"]
                if field not in gate
            ]
            if missing_gate_fields:
                errors.append(f"Phase {pid} gate {gid}: missing fields {missing_gate_fields}.")
            operator = str(gate.get("operator", ""))
            if operator not in ALLOWED_OPERATORS:
                errors.append(f"Phase {pid} gate {gid}: invalid operator {operator}.")

    if "Selected model: `Goose-first hybrid`." not in decision_pack_text:
        errors.append("Decision Pack missing selected model line for Goose-first hybrid.")

    if "docs/render/decision-pack-v1.md" not in phase_index_text:
        errors.append("Phase index missing decision-pack reference.")

    phase1 = (phases_root / "phase-01-stream-contract-foundation" / "README.md").read_text(encoding="utf-8")
    if "schema_version" not in phase1 or "event_id" not in phase1:
        errors.append("Phase 01 README must explicitly include schema_version and event_id.")

    phase4 = (phases_root / "phase-04-inmemory-actor-checkpointing" / "README.md").read_text(encoding="utf-8")
    if "mini-journal" not in phase4:
        errors.append("Phase 04 README must include mini-journal durability constraint.")

    phase12 = (phases_root / "phase-12-data-volume-and-heavy-content-ux" / "README.md").read_text(encoding="utf-8")
    if "backend pipeline as canonical source of truth" not in phase12:
        errors.append("Phase 12 README must enforce backend canonical coalescing language.")

    phase13 = (phases_root / "phase-13-queued-follow-up-flow" / "README.md").read_text(encoding="utf-8")
    if "risk-based" not in phase13:
        errors.append("Phase 13 README must preserve risk-based confirmation policy.")

    if errors:
        print("Render freeze validation: FAIL")
        print(f"Errors: {len(errors)}")
        for err in errors:
            print(f"- {err}")
        if warnings:
            print(f"Warnings: {len(warnings)}")
            for warn in warnings:
                print(f"- {warn}")
        return 1

    print("Render freeze validation: PASS")
    print(f"Validated phases: {len(EXPECTED_PHASE_IDS)}")
    print(f"Validated contracts: {len(EXPECTED_CONTRACTS)}")
    print("System-freeze artifacts and phase docs are aligned.")
    if warnings:
        print(f"Warnings: {len(warnings)}")
        for warn in warnings:
            print(f"- {warn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
