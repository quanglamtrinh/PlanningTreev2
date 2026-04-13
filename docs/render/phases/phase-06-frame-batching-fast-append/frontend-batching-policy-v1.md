# Frontend Batching Policy v1

Status: Frozen artifact for `frontend_batching_policy_frozen`.

Date: 2026-04-13.

Phase: `phase-06-frame-batching-fast-append` (C01, C07).

## Policy Goals

1. Reduce frontend apply frequency under burst stream traffic.
2. Preserve canonical backend semantics and ordering guarantees.
3. Keep reconnect and replay behavior deterministic under C1/C2.

## Core Rules

1. Batching is presentation-only:
   - event queueing and frame flush do not change event meaning.
   - no semantic coalescing in frontend state ownership.
2. Ordering remains deterministic:
   - events are applied in arrival order within each flush cycle.
   - no out-of-order merge across replay/live boundaries.
3. Contract compatibility:
   - no C1 envelope field/type changes.
   - no C2 cursor semantics changes.

## Force Flush Rules

Frontend must support immediate flush (bypass normal frame cadence) for:

- terminal stream transitions (`stream_closed`, final completion/error boundaries).
- user-visible critical transitions where deferred render would break UX correctness.
- reconnect/resync boundaries before replay/live handoff continues.

## Fast Append Eligibility and Fallback

1. Fast append path is allowed only when all guard checks pass:
   - target item slot is known and already present.
   - incoming update is append-only text delta for the same item/turn context.
   - no structural mutation is required.
2. Fallback:
   - if any guard fails, route to generic patch/apply path immediately.
   - fallback is mandatory and must preserve final state parity with non-fast-path apply.

## Replay and Reconnect Behavior

- Last applied cursor remains source of truth for reconnect.
- Frame batching must not hide replay-miss detection or cursor progression.
- After reconnect, replay applies before live continuation with dedupe intact.

## Prohibited Behaviors

- semantic merge/coalescing in frontend that bypasses canonical backend event semantics.
- dropping queued events silently to keep UI smooth.
- fast append mutations when item identity or turn context is ambiguous.
