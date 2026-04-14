# Phase AQ6 Evidence

This directory stores Phase AQ6 gate source and aggregation artifacts.

Fixed source file names for this phase:

1. ask_reload_recovery_suite.json
1. ask_reconnect_duplicate_guard_suite.json
1. ask_reset_policy_suite.json

Gate aggregation output:

1. phase-a6-gate-report.json

Baseline reference:

1. baseline-manifest-v1.json

## Evidence Eligibility Rules

Source artifacts must include:

1. evidence_mode (candidate | synthetic)
2. gate_eligible (boolean)
3. context.candidate_path (required when evidence_mode=candidate)
4. context.candidate_commit_sha (required when evidence_mode=candidate)

Eligibility policy:

1. evidence_mode=candidate and gate_eligible=true is valid for phase closure.
2. evidence_mode=synthetic and gate_eligible=false is local dry-run only.
