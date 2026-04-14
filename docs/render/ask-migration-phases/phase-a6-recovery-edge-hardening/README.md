# Phase A6 - Recovery and Edge-case Hardening

Status: Planned.

Phase ID: `AQ6`.

## Objective

Harden ask queue behavior across reconnect, reload, reset, and failure scenarios so queued intent remains safe and deterministic.

## In Scope

1. Reload/restart safety:
   - persisted ask queue hydration rules
   - `sending -> queued` recovery semantics after reload
2. Reconnect safety:
   - queue behavior under stream reconnect and replay mismatch
3. Reset behavior:
   - explicit policy when ask thread reset occurs
4. Failure handling:
   - retry and error-state transitions remain deterministic

## Out of Scope

1. New UX features beyond hardening.
2. Production rollout policy (A7).

## Implementation Plan

1. Define ask queue storage keys and cleanup policy by thread identity.
2. Add reset hook behavior:
   - clear or rebind queue according to frozen A0 contract.
3. Add reconnect guards:
   - avoid duplicate send attempts during reconnect loops.
4. Strengthen error transitions:
   - `sending -> failed`
   - `failed -> queued` via retry/confirm action.

## Quality Gates

1. Durability:
   - no queued-entry loss on reload within supported persistence window.
2. Safety:
   - no duplicate send on reconnect/retry edges.
3. Determinism:
   - reset behavior is consistent and documented.

## Test Plan

1. Unit tests:
   - queue hydration/recovery transitions.
2. Integration tests:
   - reconnect during sending, then recovery and flush.
   - ask reset while queue has pending entries.
3. Manual checks:
   - browser refresh with queued ask entries and continued sending.

## Risks and Mitigations

1. Risk: stale storage causes wrong queue reattach.
   - Mitigation: strict key scoping and metadata validation before hydrate.
2. Risk: reset semantics surprise users.
   - Mitigation: explicit UI message and documented policy.

## Exit Criteria

1. Recovery behavior is deterministic and tested for critical edges.
2. Ask queue no longer has known high-risk failure gaps.

## Effort Estimate

- Size: Medium
- Estimated duration: 3-4 engineering days
- Suggested staffing: 1 frontend + 1 backend support

