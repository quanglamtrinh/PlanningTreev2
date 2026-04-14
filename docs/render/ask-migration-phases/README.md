# Ask Queue Migration Phase Plan (Execution -> Ask)

Status: Draft for implementation review.

Last updated: 2026-04-14.

## Purpose

This plan defines how we migrate queue-based follow-up execution patterns to the `ask_planning` lane in a controlled and quality-safe way.

The goal is parity in reliability and UX behavior, while preserving ask-lane constraints:

- ask remains read-only for workspace mutations
- ask metadata shell remains stable and transcript-independent
- execution-only workflow decisions (plan-actions and review transitions) remain execution-only

## Context Snapshot (Current State)

Current behavior in code:

1. Ask lane sends directly (no queue panel):
   - `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
2. Queue state machine is execution-only:
   - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
3. Backend route dispatch differs by lane:
   - execution turns use workflow follow-up dispatcher
   - ask turns use `thread_runtime_service_v3.start_turn(...)`
   - `backend/routes/workflow_v3.py`
4. Ask runtime is read-only and policy-guarded:
   - `backend/conversation/services/thread_runtime_service_v3.py`

## Frozen Scope Boundaries

In scope:

- bring queue-based send semantics to ask lane
- add ask-safe risk confirmation and recovery policy
- preserve ask shell and shaping workflow behavior

Out of scope:

- enabling plan-actions on ask lane
- allowing write-enabled ask runtime
- moving CTA ownership from node-detail panel into transcript feed
- changing execution/audit workflow phase machine semantics

## Governance Pack

System-freeze artifacts for this migration wave:

- `docs/render/ask-migration-phases/system-freeze/README.md`
- `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
- `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
- `docs/render/ask-migration-phases/system-freeze/contracts/README.md`

Before implementing each phase:

1. Confirm entry criteria in `phase-manifest-v1.json`.
2. Confirm gate targets in `phase-gates-v1.json`.
3. Confirm frozen contracts in `contracts/`.
4. Prepare candidate-backed evidence files in the phase `evidence/` folder.

## Global Quality Bar (all phases)

A phase is complete only when all conditions are true:

1. Correctness:
   - no message loss
   - no duplicate send under retry/reconnect paths
2. Lane safety:
   - ask remains read-only in runtime and policy enforcement
3. UX integrity:
   - ask metadata shell remains visible and stable
   - queue controls are deterministic and understandable
4. Regression safety:
   - no behavior regression for execution queue flow
5. Tests:
   - phase-specific unit/integration tests are added and passing

## Phase Sequence

1. [phase-a0-contract-freeze-ask-queue](./phase-a0-contract-freeze-ask-queue/README.md)
2. [phase-a1-backend-ask-idempotency-foundation](./phase-a1-backend-ask-idempotency-foundation/README.md)
3. [phase-a2-lane-aware-queue-core-refactor](./phase-a2-lane-aware-queue-core-refactor/README.md)
4. [phase-a3-ask-queue-mvp-auto-flush](./phase-a3-ask-queue-mvp-auto-flush/README.md)
5. [phase-a4-ask-risk-confirmation-policy](./phase-a4-ask-risk-confirmation-policy/README.md)
6. [phase-a5-ask-queue-ui-shell-integrity](./phase-a5-ask-queue-ui-shell-integrity/README.md)
7. [phase-a6-recovery-edge-hardening](./phase-a6-recovery-edge-hardening/README.md)
8. [phase-a7-test-matrix-controlled-enablement](./phase-a7-test-matrix-controlled-enablement/README.md)

## Dependency Order

1. A0 freezes contract and policy targets.
2. A1 establishes backend dedupe safety before queue expansion.
3. A2 refactors queue core to lane-aware architecture.
4. A3 enables ask queue baseline behavior.
5. A4 adds risk confirmation protections for stale intents.
6. A5 adds ask queue UX surface and shell compatibility safeguards.
7. A6 hardens recovery for reconnect/reload/reset/failure edges.
8. A7 finalizes test matrix and controlled enablement.

## Suggested Delivery Rhythm

1. Keep each phase in small PR slices (schema, store, UI, tests).
2. Do not start A3 before A1 and A2 are merged.
3. Maintain an execution-regression suite run in every ask phase.
4. Track carry-over debt explicitly in each phase closeout.
