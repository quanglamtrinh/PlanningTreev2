# Phase 07 Evidence

This directory stores Phase 07 preflight and gate artifacts.

Fixed source file names for Phase 07 gate inputs:

1. `state_hot_path_benchmark.json`
2. `state_hot_path_trace.json`
3. `reducer_identity_tests.json`

Gate aggregation output:

1. `phase07-gate-report.json`

Baseline reference:

1. `baseline-manifest-v1.json`

## Hardening Rules (Pre-Phase-8)

Source artifacts (`state_hot_path_benchmark.json`, `state_hot_path_trace.json`, `reducer_identity_tests.json`) must include:

1. `evidence_mode` (`candidate` | `synthetic`)
2. `gate_eligible` (boolean)
3. `context.candidate_path` (required when `evidence_mode=candidate`)
4. `context.candidate_commit_sha` (required when `evidence_mode=candidate`)

Eligibility policy:

1. `evidence_mode=candidate` + `gate_eligible=true` -> allowed for phase gate closure.
2. `evidence_mode=synthetic` + `gate_eligible=false` -> local dry-run only, not valid for closure.

Gate report (`phase07-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
