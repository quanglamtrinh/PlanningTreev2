# Phase A2 - Lane-aware Queue Core Refactor

Status: Planned.

Phase ID: `AQ2`.

## Objective

Refactor queue internals from execution-only assumptions to a lane-aware queue engine reusable for both execution and ask.

## Why This Phase Matters

Current queue code is tightly coupled to execution workflow fields and role checks. Directly adding ask logic on top would increase complexity and regression risk.

## In Scope

1. Introduce lane-aware queue domain model:
   - queue state keyed by lane/role
   - lane-specific policy adapter hooks
2. Extract common queue operations:
   - enqueue
   - reorder
   - remove
   - send-now
   - retry
   - confirm
3. Keep execution policy behavior unchanged through adapter implementation.
4. Preserve storage persistence contract (or provide migration shim).

## Out of Scope

1. Ask queue UI exposure.
2. Ask auto-flush policy details.
3. Backend idempotency logic changes (done in A1).

## Implementation Plan

1. Store architecture:
   - split queue core logic from execution-specific gating logic.
2. Policy abstraction:
   - `evaluatePauseReason(role, state)`
   - `sendWindowIsOpen(role, state, options)`
   - `requiresConfirmation(role, entry, context)`
3. Data compatibility:
   - migration for existing execution queue localStorage shape if needed.
4. Regression harness:
   - run existing execution queue tests against refactored core.

## Frozen Inputs (A2 kickoff)

1. `preflight-v1.md`
2. `lane-aware-queue-core-contract-freeze-v1.md`
3. `../system-freeze/contracts/aqc1-ask-queue-core-contract-v1.md`
4. `../system-freeze/contracts/aqc3-ask-send-window-contract-v1.md`
5. `kickoff-checklist-v1.md`

## Quality Gates

1. Execution parity:
   - all existing execution queue tests remain green.
2. Refactor quality:
   - no behavior change in execution send window and confirmation flow.
3. Maintainability:
   - queue core and lane policy boundaries are explicit and documented.

## Test Plan

1. Unit tests:
   - generic queue state transitions via lane-neutral test matrix.
2. Regression tests:
   - replay existing execution scenarios on new core.
3. Snapshot tests:
   - serialized queue state migration/hydration compatibility.

## Risks and Mitigations

1. Risk: subtle execution regression during abstraction.
   - Mitigation: golden behavior tests from current execution policy.
2. Risk: over-abstraction increases complexity.
   - Mitigation: only extract proven shared logic; keep lane-specific code in adapters.

## Exit Criteria

1. Queue core is lane-aware and execution behavior is preserved.
2. Ask can be enabled in A3 without duplicated queue implementations.

## Effort Estimate

- Size: Medium
- Estimated duration: 3-5 engineering days
- Suggested staffing: 1 frontend primary + 1 reviewer
