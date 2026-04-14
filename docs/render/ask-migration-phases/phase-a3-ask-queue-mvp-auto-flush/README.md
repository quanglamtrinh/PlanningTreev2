# Phase A3 - Ask Queue MVP and Auto-flush Baseline

Status: Planned.

Phase ID: `AQ3`.

## Objective

Enable queue-based sending in ask lane with a minimal, deterministic auto-flush policy.

## Target Behavior

When user sends message in ask tab:

1. message is enqueued first
2. queue flushes automatically when send window is open
3. if send window is blocked, message remains queued (not lost)

## In Scope

1. Ask tab send path switches from direct send to queue-first path.
2. Ask lane auto-flush baseline policy:
   - snapshot exists
   - no active turn
   - processing state is idle
   - no unresolved/pending user input request
3. Ask queue persistence and hydration baseline.
4. Keep execution queue behavior unchanged.

## Out of Scope

1. Risk confirmation (A4).
2. Queue control panel parity UI (A5).
3. Advanced reconnect/reset hardening (A6).

## Implementation Plan

1. Hook ask composer send into lane-aware `enqueue`.
2. Add ask lane policy adapter with baseline `sendWindowIsOpen`.
3. Trigger flush on:
   - enqueue
   - relevant snapshot lifecycle transitions
   - stream reopen with healthy state
4. Maintain backend start-turn call with idempotency key.

## Quality Gates

1. Reliability:
   - rapid multi-send in ask does not drop messages.
2. Ordering:
   - send order matches queue order.
3. Safety:
   - no duplicate turn creation in retry scenarios.

## Test Plan

1. Unit tests:
   - ask enqueue + auto-flush transition cases.
2. Integration tests:
   - ask active turn then queued follow-up flush after completion.
3. Manual checks:
   - quick repeated sends in ask tab under normal network and reconnect.

## Risks and Mitigations

1. Risk: ask queue never flushes due to over-strict window.
   - Mitigation: explicit diagnostics for pause reason and test matrix for transitions.
2. Risk: flush race with stream update.
   - Mitigation: single-flight send invariant in queue core.

## Exit Criteria

1. Ask lane supports queue-first sending with deterministic auto-flush.
2. Execution lane behavior remains unchanged.

## Effort Estimate

- Size: Medium
- Estimated duration: 3-4 engineering days
- Suggested staffing: 1 frontend primary + 1 backend support

