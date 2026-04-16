# Phase A6 - Recovery and Edge-case Hardening

Status: Completed.

Phase ID: `AQ6`.

Date completed: 2026-04-15.

## Completion Snapshot

1. Ask queue recovery logic is hardened for reload/reconnect/reset/failure paths.
2. Ask queue hydration keeps strict thread-key scoping and deterministic status normalization:
   - `sending -> queued`
   - `requires_confirmation` preserved across reload
3. Ask reconnect behavior keeps single-flight safety and prevents duplicate head dispatch across reconnect loops.
4. Ask thread route mismatch (`invalid_request`) after reset is classified and handled by policy:
   - clear ask queue (no rebind)
   - persist cleared queue
   - mark stream/state mismatch-safe pause state
5. Ask by-id reset behavior is explicit and deterministic:
   - supported only for `ask_planning`
   - clears ask snapshot state
   - publishes workflow update event to refresh workflow/detail bridges
6. AQ6 evidence automation and gate report are delivered and pass.

## Objective

Harden ask queue behavior across reconnect, reload, reset, and failure scenarios so queued intent remains safe and deterministic.

## In Scope

1. Reload/restart safety:
   - persisted ask queue hydration rules
   - `sending -> queued` recovery semantics after reload
2. Reconnect safety:
   - queue behavior under stream reconnect and replay mismatch
3. Reset behavior:
   - explicit reset policy under ask thread mismatch paths
4. Failure handling:
   - retry and error-state transitions remain deterministic

## Out of Scope

1. New UX features beyond hardening.
2. Production rollout policy (A7).
3. Observability/rollout-safety layer expansion beyond frozen AQ6 contracts.

## Implementation Plan

1. Harden ask queue recovery transitions in `threadByIdStoreV3`.
2. Enforce reset-by-id policy consistency in backend `workflow_v3`.
3. Add AQ6 candidate-backed source evidence generators and gate report automation.
4. Keep execution queue behavior and audit-lane read-only boundaries unchanged.

## Quality Gates

1. Durability:
   - no queued-entry loss on reload within supported persistence window.
2. Safety:
   - no duplicate send on reconnect/retry edges.
3. Determinism:
   - reset behavior is consistent and documented.

## Test Plan

1. Frontend unit tests:
   - hydration/recovery transitions and mismatch reset handling.
2. Backend integration tests:
   - reset-by-id contract, idempotency scope after reset, workflow update publish.
3. Evidence self-tests:
   - AQ6 source suites and gate report contract checks.

## Risks and Mitigations

1. Risk: stale storage causes wrong queue reattach.
   - Mitigation: strict storage key scoping by project/node/thread and normalized hydrate transitions.
2. Risk: reset mismatch causes stale UI state.
   - Mitigation: backend workflow update publish plus frontend mismatch classification and queue clear policy.

## Exit Criteria

1. Recovery behavior is deterministic and test-covered for AQ6 paths.
2. AQ6 gate sources are candidate-backed, gate-eligible, and passing.
3. No known A6 blocker remains before A7 handoff.
