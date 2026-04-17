# Phase A4 - Ask Risk Confirmation Policy

Status: Completed.

Phase ID: `AQ4`.

Date completed: 2026-04-15.

## Completion Snapshot

1. Ask stale-intent risk policy is active in runtime:
   - `queued -> requires_confirmation` when AQC4 triggers match (`stale_age`, `thread_drift`, `snapshot_drift`, `stale_marker`)
   - head `requires_confirmation` blocks downstream auto-flush (strict FIFO)
2. Lane-aware ask controls are active:
   - `confirmQueued(entryId)` restamps ask context/timestamp and retries flush immediately
   - `removeQueued(entryId)` removes blocked head and retries flush immediately
3. Ask persistence behavior is updated for A4:
   - hydrate preserves ask `requires_confirmation`
   - hydrate still normalizes ask `sending -> queued`
4. A4-minimal UI is active in ask tab:
   - blocked-head inline strip above composer
   - reason label + actions `Confirm & send` and `Discard`
5. AQ4 gate evidence is generated in canonical phase folder and passes.

## Objective

Introduce ask-specific stale-intent safeguards so queued ask messages are not auto-sent in risky context changes.

## Why Separate from A3

A3 proves baseline queue operation. A4 adds policy complexity (confirmation gating) without mixing with first enablement risk.

## In Scope

1. Define ask confirmation triggers for `requires_confirmation` state.
2. Add explicit confirm action semantics for ask queue.
3. Ensure auto-flush skips `requires_confirmation` entries.
4. Keep execution confirmation policy unchanged.

## Proposed Ask Risk Triggers

1. Age trigger:
   - queued item older than configured threshold.
2. Thread reset/context shift trigger:
   - queued entry context differs from current ask thread context.
3. Shaping context drift trigger:
   - key shaping revision marker changed since enqueue (for example frame/spec revision pointers).

## Out of Scope

1. UI panel redesign (A5 owns ask queue controls UX).
2. Reconnect/reset hardening edge cases (A6 owns full hardening).

## Implementation Plan

1. Add ask queue context snapshot at enqueue time.
2. Implement `queueEntryRequiresConfirmation` for ask adapter.
3. Add transition:
   - `queued -> requires_confirmation` when risk detected.
4. Add confirm path:
   - confirm restamps context and returns entry to eligible queued state.

## Quality Gates

1. Safety:
   - stale/risky ask entries never auto-send.
2. Determinism:
   - confirmation transitions are reproducible and testable.
3. Non-regression:
   - execution confirmation policy behavior remains intact.

## Test Plan

1. Unit tests:
   - age/context drift trigger matrix.
2. Integration tests:
   - enqueue, mutate context, verify confirmation required before send.
3. Manual checks:
   - user can recover with explicit confirm and then send successfully.

## Risks and Mitigations

1. Risk: too many false positives (excessive confirmation friction).
   - Mitigation: start conservative trigger set and tune with canary feedback.
2. Risk: hidden trigger ambiguity.
   - Mitigation: expose clear reason label in queue state for each confirmation requirement.

## Exit Criteria

1. Ask risk policy is enforced and covered by tests.
2. No stale-intent auto-send path remains.

## Effort Estimate

- Size: Medium
- Estimated duration: 2-4 engineering days
- Suggested staffing: 1 frontend primary
