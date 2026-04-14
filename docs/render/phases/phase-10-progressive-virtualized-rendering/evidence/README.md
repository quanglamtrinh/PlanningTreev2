# Phase 10 Evidence

This directory stores Phase 10 gate source and aggregation artifacts.

Fixed source file names for Phase 10 gate inputs:

1. `long_thread_open_scenario.json`
2. `scroll_smoothness_profile.json`
3. `virtualization_anchor_tests.json`

Gate aggregation output:

1. `phase10-gate-report.json`

Baseline reference:

1. `baseline-manifest-v1.json`

## Evidence Eligibility Rules

Source artifacts (`long_thread_open_scenario.json`, `scroll_smoothness_profile.json`, `virtualization_anchor_tests.json`) must include:

1. `evidence_mode` (`candidate` | `synthetic`)
2. `gate_eligible` (boolean)
3. `context.candidate_path` (required when `evidence_mode=candidate`)
4. `context.candidate_commit_sha` (required when `evidence_mode=candidate`)

Eligibility policy:

1. `evidence_mode=candidate` + `gate_eligible=true` -> allowed for phase gate closure.
2. `evidence_mode=synthetic` + `gate_eligible=false` -> local dry-run only, not valid for closure.

Gate report (`phase10-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
