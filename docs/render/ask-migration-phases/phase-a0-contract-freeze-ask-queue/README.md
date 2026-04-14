# Phase A0 - Contract Freeze for Ask Queue Parity

Status: Completed.

Phase ID: `AQ0`.

## Objective

Freeze contract boundaries for ask-lane queue migration before implementation, so later phases do not re-open architecture decisions.

## Why This Phase Exists

Queue logic currently carries execution-specific assumptions. If ask migration starts without a frozen contract, we risk hidden behavior drift and unstable scope.

## In Scope

1. Freeze Ask Queue Contract v1 (state machine and send-window rules).
2. Freeze ask parity definition:
   - parity for send reliability and queue UX
   - no parity for execution-only plan-actions
3. Freeze safety constraints:
   - ask remains read-only
   - ask shell stays metadata-driven
4. Freeze backward compatibility behavior for execution queue flow.

## Out of Scope

1. No runtime code changes.
2. No UI queue controls implementation.
3. No backend idempotency implementation.

## Contract Decisions to Freeze

1. Lane capabilities:
   - execution: unchanged
   - ask: queue-enabled send path
   - audit: remains read-only/no queue
2. Ask send-window baseline:
   - queue can auto-flush only when lane is idle and not blocked by active request
3. Confirmation policy ownership:
   - stale-intent checks handled by ask queue policy (not by execution policy reuse alone)
4. Reset semantics:
   - ask thread reset behavior for queued entries must be explicit (clear vs rebind)

## Deliverables

1. `ask-queue-contract-v1.md` (state machine + transitions + invariants).
2. `ask-queue-gating-matrix-v1.md` (send-window and block reasons).
3. `ask-queue-risk-baseline-v1.md` (initial stale-intent triggers).

## Quality Gates

1. Architecture gate:
   - no open critical decision remains for A1-A3.
2. Scope gate:
   - contract explicitly marks in-scope vs out-of-scope behavior.
3. Compatibility gate:
   - execution queue flow listed as must-not-regress baseline.

## Test Plan

1. N/A for code tests in this phase.
2. Review checklist:
   - backend owner sign-off
   - frontend owner sign-off
   - workflow owner sign-off

## Risks and Mitigations

1. Risk: contract too broad and blocks delivery.
   - Mitigation: freeze minimal viable contract for A1-A3; defer optional behavior.
2. Risk: hidden coupling to execution workflow remains undocumented.
   - Mitigation: explicitly map integration touchpoints in deliverables.

## Exit Criteria

1. Contract artifacts merged and approved.
2. Next phases can implement without reopening core policy questions.

## Closure Artifact

1. `docs/render/ask-migration-phases/phase-a0-contract-freeze-ask-queue/close-phase-v1.md`

## Effort Estimate

- Size: Small
- Estimated duration: 1-2 engineering days
- Suggested staffing: 1 backend + 1 frontend + 1 tech lead reviewer
