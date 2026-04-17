# Ask Queue Contract v1

Status: Frozen for ask migration.

Last updated: 2026-04-14.

## 1. Purpose

This contract freezes the ask-lane queue behavior required for A1-A3 implementation.

Scope:

- ask send reliability and queue semantics
- no change to execution-only workflow permissions
- ask runtime remains read-only for workspace writes

## 2. Queue Entry State Set (Frozen)

Allowed ask queue entry states:

1. `queued`
2. `requires_confirmation`
3. `sending`
4. `failed`

No additional states are allowed in A1-A3.

## 3. Deterministic State Machine (Frozen)

Core transitions:

1. `enqueue` (ask lane send action):
   - `none -> queued`
2. `auto_flush_attempt` when send-window is open:
   - `queued -> sending`
3. `send_success`:
   - `sending -> removed_from_queue`
4. `send_failure`:
   - `sending -> failed`
5. `risk_detected` (before send, unconfirmed):
   - `queued -> requires_confirmation`
6. `confirm`:
   - `requires_confirmation -> queued`
7. `retry`:
   - `failed -> queued`
8. `remove`:
   - `queued | requires_confirmation | failed -> removed_from_queue`

Forbidden transitions:

1. `requires_confirmation -> sending` without explicit `confirm`.
2. Multiple entries transitioning to `sending` at the same time.

## 4. Invariants (Frozen)

1. Single-flight invariant:
   - at most one `sending` entry in ask queue.
2. Ordering invariant:
   - send order follows queue order for eligible entries.
3. Safety invariant:
   - `requires_confirmation` entries are never auto-sent.
4. Lane safety invariant:
   - ask queue flow cannot enable execution-only plan actions.
5. Runtime safety invariant:
   - ask lane remains read-only for workspace mutation operations.

## 5. Reset Semantics (Frozen)

Policy is fixed for this migration wave:

1. Ask reset must clear queued ask entries (`clear`, not `rebind`).
2. Cleared entries are not auto-restored after reset.
3. Queue clear on reset is normative for A2 and A6 implementation/testing.

## 6. Phase Dependencies

1. A1 uses this contract to add ask idempotent turn start safely.
2. A2 refactors queue core to lane-aware architecture while preserving these invariants.
3. A3 enables ask queue auto-flush using this frozen state machine.

