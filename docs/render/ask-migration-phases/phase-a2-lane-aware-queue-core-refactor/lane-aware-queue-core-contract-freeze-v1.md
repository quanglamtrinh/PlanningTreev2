# Lane-aware Queue Core Contract Freeze v1 (AQ2)

Status: Frozen for A2 implementation.

Last updated: 2026-04-14.

Marker: `lane_aware_queue_core_contract_frozen`

## 1. Purpose

Freeze the minimum adapter and queue-core boundaries required to implement AQ2 without execution regressions.

## 2. Queue Core Boundary (Frozen)

Queue core must remain lane-neutral and deterministic:

1. state transitions are pure and deterministic for the same `(lane, snapshot, queue, options)` input.
2. single-flight invariant is lane-scoped:
   - at most one `sending` entry per lane queue.
3. queue ordering is lane-scoped FIFO for eligible entries.

## 3. Lane Adapter Surface (Frozen)

AQ2 adapter contracts:

1. `evaluatePauseReason(lane, snapshot, context, options) -> pause_reason`
2. `sendWindowIsOpen(lane, snapshot, context, options) -> boolean`
3. `requiresConfirmation(lane, entry, currentContext, nowMs) -> boolean`

AQ2 does not freeze function names in code, but it freezes these semantic responsibilities.

## 4. Execution Adapter Compatibility (Frozen)

Execution behavior must remain equivalent to pre-AQ2 behavior:

1. same pause-gate semantics for:
   - `workflow_blocked`
   - `runtime_waiting_input`
   - `plan_ready_gate`
   - `operator_pause`
2. same confirmation triggers for stale entry age/context drift.
3. same queue control behavior (`reorder`, `remove`, `send now`, `confirm`, `retry`).

## 5. Ask Adapter Readiness Target (A2 only)

AQ2 prepares ask adapter plumbing but does not enable ask queue UI or ask auto-flush policy changes (A3).

Ask pause reason set to preserve for A3:

1. `snapshot_unavailable`
2. `stream_or_state_mismatch`
3. `active_turn_running`
4. `waiting_user_input`
5. `operator_pause`

Reference: `phase-a0-contract-freeze-ask-queue/ask-queue-gating-matrix-v1.md`.

## 6. Persistence Compatibility (Frozen)

1. Existing execution queue localStorage data must remain readable.
2. If storage shape is changed in AQ2, a migration shim is mandatory.
3. Migration must be deterministic and non-lossy for supported fields.

## 7. Out-of-scope Guardrails

AQ2 must not:

1. enable ask queue panel UI.
2. change ask runtime read-only constraints.
3. alter backend ask idempotency behavior from AQ1.

