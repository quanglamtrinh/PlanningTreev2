# Phase 11 Evidence

This directory stores Phase 11 gate source and aggregation artifacts.

Fixed source file names for Phase 11 gate inputs:

1. `heavy_payload_profile.json`
2. `worker_versioning_tests.json`
3. `heavy_content_interaction_smoke.json`

Gate aggregation output:

1. `phase11-gate-report.json`

Baseline reference:

1. `baseline-manifest-v1.json`

## Evidence Eligibility Rules

Source artifacts must include:

1. `evidence_mode` (`candidate` | `synthetic`)
2. `gate_eligible` (boolean)
3. `context.candidate_path` (required when `evidence_mode=candidate`)
4. `context.candidate_commit_sha` (required when `evidence_mode=candidate`)

Eligibility policy:

1. `evidence_mode=candidate` + `gate_eligible=true` -> allowed for phase gate closure.
2. `evidence_mode=synthetic` + `gate_eligible=false` -> local dry-run only, not valid for closure.

Gate report (`phase11-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
