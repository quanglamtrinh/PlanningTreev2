# Phase 09 Evidence

This directory stores Phase 09 gate source and aggregation artifacts.

Fixed source file names for Phase 09 gate inputs:

1. `row_render_profile.json`
2. `parse_cache_trace.json`
3. `ui_regression_suite.json`

Gate aggregation output:

1. `phase09-gate-report.json`

Baseline reference:

1. `baseline-manifest-v1.json`

## Evidence Eligibility Rules

Source artifacts (`row_render_profile.json`, `parse_cache_trace.json`, `ui_regression_suite.json`) must include:

1. `evidence_mode` (`candidate` | `synthetic`)
2. `gate_eligible` (boolean)
3. `context.candidate_path` (required when `evidence_mode=candidate`)
4. `context.candidate_commit_sha` (required when `evidence_mode=candidate`)

Eligibility policy:

1. `evidence_mode=candidate` + `gate_eligible=true` -> allowed for phase gate closure.
2. `evidence_mode=synthetic` + `gate_eligible=false` -> local dry-run only, not valid for closure.

Gate report (`phase09-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
