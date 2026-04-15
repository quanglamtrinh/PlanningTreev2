# Phase AQ3 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a3-ask-queue-mvp-auto-flush.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a2_passed
2. ask_send_window_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
2. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
3. docs/render/ask-migration-phases/system-freeze/contracts/README.md
4. docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md
5. docs/render/ask-migration-phases/system-freeze/contracts/aqc2-ask-idempotency-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_queue_state_machine_suite -> ask_queued_message_loss_events (lte 0 count)
2. ask_queue_order_integration -> ask_queue_order_violation_events (lte 0 count)
3. ask_auto_flush_scenarios -> ask_auto_flush_success_rate_pct (gte 98 pct)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_state_machine_suite.json
2. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_order_integration.json
3. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_auto_flush_scenarios.json
4. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/phase-a3-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Go/No-Go Checklist

Must-exist markers:

1. `phase_a2_passed` exists in:
   - docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/close-phase-v1.md
2. `ask_send_window_contract_frozen` exists in:
   - docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md

Must-pass commands:

1. `npm run check:ask_migration_freeze`
2. `npm run test:unit --prefix frontend -- threadQueueCoreV3.test.ts threadQueuePolicyAdaptersV3.test.ts`
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts`

Operational note:

1. Run queue/unit tests using `--prefix frontend` to avoid root-level `npx vitest` cwd drift.

## 6. Preflight Exit

No open preflight blocker remains once entry criteria, marker checks, required commands, and gate sources above are all green.
