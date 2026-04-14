# Phase AQ7 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a7-test-matrix-controlled-enablement.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a6_passed
1. ask_rollout_gate_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc7-ask-rollout-gate-contract-v1.md
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_queue_acceptance_matrix -> ask_queue_acceptance_suite_pass_rate_pct (gte 100 pct)
1. ask_canary_stability_report -> ask_canary_blocker_incidents (lte 0 count)
1. ask_rollback_drill_report -> ask_rollback_drill_failures (lte 0 count)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_queue_acceptance_matrix.json
1. docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_canary_stability_report.json
1. docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_rollback_drill_report.json
1. docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/phase-a7-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
