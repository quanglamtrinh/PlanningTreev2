# Phase 08 Evidence

This directory stores Phase 08 gate source and aggregation artifacts.

Fixed source file names for Phase 08 gate inputs:

1. `render_fanout_profile.json`
2. `stream_resilience_scenario.json`
3. `reload_reason_audit.json`

Gate aggregation output:

1. `phase08-gate-report.json`

Baseline reference:

1. `baseline-manifest-v1.json`

## Evidence Eligibility Rules

Source artifacts (`render_fanout_profile.json`, `stream_resilience_scenario.json`, `reload_reason_audit.json`) must include:

1. `evidence_mode` (`candidate` | `synthetic`)
2. `gate_eligible` (boolean)
3. `context.candidate_path` (required when `evidence_mode=candidate`)
4. `context.candidate_commit_sha` (required when `evidence_mode=candidate`)

Eligibility policy:

1. `evidence_mode=candidate` + `gate_eligible=true` -> allowed for phase gate closure.
2. `evidence_mode=synthetic` + `gate_eligible=false` -> local dry-run only, not valid for closure.

Gate report (`phase08-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
