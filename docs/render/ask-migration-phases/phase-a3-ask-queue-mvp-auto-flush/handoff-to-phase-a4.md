# Phase A3 to Phase A4 Handoff

Status: Ready for execution handoff (all AQ3 gates passed).

Date: 2026-04-15.

Source phase: `phase-a3-ask-queue-mvp-auto-flush` (`AQ3`).

Target phase: `phase-a4-ask-risk-confirmation-policy` (`AQ4`).

## 1. Handoff Summary

Phase A3 ask queue MVP is complete and validated:

1. Ask lane now enqueues first and auto-flushes deterministically when send window is open.
2. Ask queue persistence/hydration baseline is active with recovery-safe status normalization.
3. Ask queue flush is wired to enqueue, stream-open/open, post-event-apply, and post-hydration eligibility checks.
4. Composer ask tab remains writable during active turns so users can queue follow-ups.
5. A3 intentionally keeps confirmation policy disabled in runtime (deferred to A4).

## 2. Guarantees Intended for Phase A4

Phase A4 may assume:

1. Ask queue-first runtime orchestration is live and stable for `queued -> sending -> removed/failed`.
2. Ask lane single-flight send invariant is enforced (`max 1 sending`).
3. Failed head entry blocks downstream auto-flush until explicit recovery action in later phases.
4. AQC3 pause-reason ordering and send-window gating semantics are deterministic.
5. Existing backend idempotency behavior from A1 remains unchanged and available for queued ask dispatch.

## 3. Canonical Inputs for A4

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc4-ask-confirmation-risk-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md`

A3 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_state_machine_suite.json`
3. `docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_queue_order_integration.json`
4. `docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/ask_auto_flush_scenarios.json`
5. `docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/phase-a3-gate-report.json`

## 4. Validation Snapshot

Completed checks:

1. `npm run check:ask_migration_freeze` -> pass.
2. `npm run test:unit --prefix frontend -- threadQueueCoreV3.test.ts threadQueuePolicyAdaptersV3.test.ts` -> pass.
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts` -> pass.
4. `npm run test:unit --prefix frontend -- BreadcrumbChatViewV2.test.tsx` -> pass.
5. `npm run typecheck --prefix frontend` -> pass.
6. `python scripts/ask_phase_a3_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a3-ask-queue-mvp-auto-flush/evidence/candidates` -> pass.

## 5. Entry Marker for A4

`phase_a3_passed`

This marker is established by A3 closeout and is ready for A4 preflight entry checks.
