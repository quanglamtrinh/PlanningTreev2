# Phase 12 Evidence

This directory stores Phase 12 gate source and aggregation artifacts.

Fixed source file names for Phase 12 gate inputs:

1. `long_session_volume_tests.json`
2. `heavy_row_classification_suite.json`
3. `preview_to_full_navigation_tests.json`

Gate aggregation output:

1. `phase12-gate-report.json`

Adaptive-cap source context requirement for `long_session_volume_tests.json`:

1. `context.resolved_profile`
2. `context.effective_hard_cap_min`
3. `context.effective_hard_cap_max`
4. `context.overflow_events_under_adaptive_cap`

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

Gate report (`phase12-gate-report.json`) fails if any source artifact is not candidate-backed and gate-eligible.
