# C6 Queue Contract v1

Status: Frozen follow-up queue behavior contract.

Owner: frontend queue UX + backend send orchestration.

## Scope

Defines queue state machine, lifecycle-driven pause/resume policy, queue controls, and stale-intent safeguards.

## Required Behaviors

1. Queue transitions are deterministic and testable.
2. Pause/resume behavior follows lifecycle/gating contract (C3).
3. Queue controls include reorder/remove/send-now.
4. No queued-message loss is allowed.
5. Confirmation policy is risk-based.

## Risk-Based Confirmation Baseline

- auto-send allowed for short queue age and low-risk context
- explicit re-confirm required when queue age threshold or context-change threshold is crossed

## Prohibited Behaviors

- hidden auto-send after long delay without policy check
- queue order mutation without explicit user/system transition
- sending while in forbidden gated states

