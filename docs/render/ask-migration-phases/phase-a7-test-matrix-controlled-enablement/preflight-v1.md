# Phase AQ7 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-15.

Phase: `phase-a7-test-matrix-controlled-enablement`.

## 1. Entry Criteria Lock

From `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`:

1. `phase_a6_passed`
2. `ask_rollout_gate_contract_frozen`

## 2. Required Frozen Inputs

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/README.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc7-ask-rollout-gate-contract-v1.md`

## 3. Gate and Evidence Lock

Phase gate sources (from `phase-gates-v1.json`):

1. `ask_queue_acceptance_matrix` -> `ask_queue_acceptance_suite_pass_rate_pct` (`gte 100 pct`)
2. `ask_canary_stability_report` -> `ask_canary_blocker_incidents` (`lte 0 count`)
3. `ask_rollback_drill_report` -> `ask_rollback_drill_failures` (`lte 0 count`)

Canonical outputs:

1. `docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_queue_acceptance_matrix.json`
2. `docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_canary_stability_report.json`
3. `docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/ask_rollback_drill_report.json`
4. `docs/render/ask-migration-phases/phase-a7-test-matrix-controlled-enablement/evidence/phase-a7-gate-report.json`

Eligibility policy:

1. `evidence_mode=candidate` with `gate_eligible=true` is required for phase closure.
2. `evidence_mode=synthetic` with `gate_eligible=false` is local dry-run only.

## 4. Mandatory AQ7 Automation Entry Points

1. `scripts/ask_phase_a7_acceptance_matrix.py`
2. `scripts/ask_phase_a7_canary_stability_report.py`
3. `scripts/ask_phase_a7_rollback_drill_report.py`
4. `scripts/ask_phase_a7_gate_report.py`
5. `npm run check:ask_phase_a7_evidence`

## 5. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 6. Standard Validation Sequence (AQ7)

Run in this fixed order:

1. `npm run check:freeze_all`
2. `npm run typecheck --prefix frontend`
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts BreadcrumbChatViewV2.test.tsx`
4. `python -m pytest backend/tests/unit/test_ask_v3_rollout_phase6_7.py`
5. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "ask_reset_by_id_clears_thread_snapshot or ask_reset_by_id_publishes_workflow_update or ask_idempotency_scope_does_not_cross_reset_to_new_thread"`
6. `npm run check:ask_phase_a7_evidence`

## 7. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
