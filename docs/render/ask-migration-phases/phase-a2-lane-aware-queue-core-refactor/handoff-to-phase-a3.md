# Phase A2 to Phase A3 Handoff

Status: Ready for execution handoff (all AQ2 gates passed).

Date: 2026-04-15.

Source phase: `phase-a2-lane-aware-queue-core-refactor` (`AQ2`).

Target phase: `phase-a3-ask-queue-mvp-auto-flush` (`AQ3`).

## 1. Handoff Summary

Phase A2 queue-core refactor is complete and validated:

1. Queue core is lane-aware and deterministic.
2. Execution queue behavior remains parity-safe after refactor.
3. Ask lane adapter plumbing is present and aligned with frozen A0/AQC3 semantics.
4. Ask queue runtime path is still not enabled in A2 (no queue panel and no auto-flush activation).
5. Canonical AQ2 evidence is candidate-backed and gate-eligible.

## 2. Guarantees Intended for Phase A3

Phase A3 may assume:

1. Lane-neutral queue transition surface is available and stable for enqueue/remove/reorder/send-state transitions.
2. Policy adapter boundary is stable and can be extended for ask auto-flush orchestration without changing execution policy behavior.
3. Execution selectors/actions and persistence shape remain backward-compatible.
4. Backend ask idempotency foundation from A1 remains unchanged and available for queue-first ask send path.
5. Ask runtime write constraints remain unchanged (read-only for workspace writes).

## 3. Canonical Inputs for A3

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc2-ask-idempotency-contract-v1.md`

A2 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/execution_queue_regression_suite.json`
3. `docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/lane_adapter_contract_tests.json`
4. `docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/queue_state_machine_determinism.json`
5. `docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/phase-a2-gate-report.json`

## 4. Validation Snapshot

Completed checks:

1. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts` -> pass.
2. `npm run test:unit --prefix frontend -- BreadcrumbChatViewV2.test.tsx` -> pass.
3. `npx vitest run tests/unit/threadQueueCoreV3.test.ts tests/unit/threadQueuePolicyAdaptersV3.test.ts` -> pass.
4. `npm run check:ask_migration_freeze` -> pass.
5. `python scripts/ask_phase_a2_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/candidates` -> pass.

## 5. Entry Marker for A3

`phase_a2_passed`

This marker is established by A2 closeout and is ready for A3 preflight entry checks.
