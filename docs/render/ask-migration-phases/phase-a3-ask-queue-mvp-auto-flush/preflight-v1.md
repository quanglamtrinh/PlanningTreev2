# Phase AQ3 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a3-ask-queue-mvp-auto-flush.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a2_passed
1. ask_send_window_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc2-ask-idempotency-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_queue_state_machine_suite -> ask_queued_message_loss_events (lte 0 count)
1. ask_queue_order_integration -> ask_queue_order_violation_events (lte 0 count)
1. ask_auto_flush_scenarios -> ask_auto_flush_success_rate_pct (gte 98 pct)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_state_machine_suite.json
1. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_order_integration.json
1. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_auto_flush_scenarios.json
1. docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/phase-a3-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
