# Phase AQ1 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a1-backend-ask-idempotency-foundation.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a0_passed
1. ask_idempotency_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc2-ask-idempotency-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_idempotency_integration -> ask_duplicate_turn_events (lte 0 count)
1. ask_retry_replay_suite -> ask_idempotent_replay_success_rate_pct (gte 99 pct)
1. ask_start_turn_latency_probe -> ask_start_turn_latency_regression_pct (lte 10 pct)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_idempotency_integration.json
1. docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_retry_replay_suite.json
1. docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_start_turn_latency_probe.json
1. docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/phase-a1-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
