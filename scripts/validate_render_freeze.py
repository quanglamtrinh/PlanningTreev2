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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all(text: str, required_fragments: list[str]) -> list[str]:
    missing: list[str] = []
    for fragment in required_fragments:
        if fragment not in text:
            missing.append(fragment)
    return missing


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
        freeze_root / "contracts" / "c1-event-stream-bridge-policy-v1.md",
        freeze_root / "contracts" / "c2-replay-resync-contract-v1.md",
        freeze_root / "contracts" / "c3-lifecycle-gating-contract-v1.md",
        freeze_root / "contracts" / "c4-durability-contract-v1.md",
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

