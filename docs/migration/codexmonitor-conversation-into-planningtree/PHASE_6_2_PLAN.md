# Phase 6.2 Plan: Concurrency, Reconnect, And Replay Robustness

## Inheritance
- This subphase inherits all Phase 6 entry conditions, invariants, gate rules, and cleanup boundaries from `PHASE_6_PLAN.md`.
- It narrows Phase 6 to isolation, reconnect, guarded refresh, and replay robustness only.

## Summary
- Phase 6.2 proves that the migrated conversation-v2 path stays isolated under concurrent activity and remains durable-store-first under reconnect, refresh, reload, and restart stress.
- This subphase does not add new conversation semantics or new product flows.
- It is complete only when:
  - `P6.2-G1` the concurrency and replay matrix is locked
  - `P6.2-G2` workspace, thread, turn, and request isolation is proven
  - `P6.2-G3` reconnect stress behavior is proven and any revealed race is hardened
  - `P6.2-G4` guarded refresh is proven recovery-only
  - `P6.2-G5` replay after refresh, reload, and restart reconstructs the same semantic state as the live path
  - `P6.2-G6` the full stress suite passes and `P6-OI-003` plus `P6-OI-004` can be closed

## Source Context Anchors
- `src/services/events.ts`
- `src/features/app/hooks/appServerEventRouter.ts`
- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/app/hooks/useRemoteThreadLiveConnection.ts`
- `src/features/threads/hooks/useThreadActions.ts`
- `src/features/threads/hooks/useThreadTurnEvents.ts`
- `src/features/threads/hooks/useThreadMessaging.ts`
- `src/features/threads/hooks/useThreads.ts`

## Gate Model
Gates:
- `P6.2-G1` - concurrency, reconnect, and replay matrix is recorded
- `P6.2-G2` - mixed workspace, thread, turn, and request isolation is proven
- `P6.2-G3` - reconnect race scenarios pass with no stale attach or wrong-state flip
- `P6.2-G4` - guarded refresh paths are proven recovery-only
- `P6.2-G5` - replay fidelity after refresh, reload, and restart is proven durable-store-first
- `P6.2-G6` - end-to-end stress validation and docs closeout both pass

The shared validation matrix must cover:
- active workspace
- active thread
- active turn
- request identity
- live subscription key
- visibility and focus state
- recovery trigger:
  - `thread-switch`
  - `focus`
  - `detached-recovery`
  - `connected-recovery`
  - manual refresh

Each matrix row must name:
- source event or trigger
- expected durable source of truth
- expected live-side behavior
- forbidden failure mode
- proving test surface

## Proof Surfaces
Required proof surfaces:
- pure router tests for `appServerEventRouter.ts`
- shared listener tests for `useAppServerEvents.tsx`
- reconnect race tests for `useRemoteThreadLiveConnection.tsx`
- thread/turn/request isolation tests across:
  - `useThreadTurnEvents.test.tsx`
  - `useThreadMessaging.test.tsx`
  - `useThreadActions.test.tsx`
  - `useThreads.integration.test.tsx`
- one focused orchestration validation harness that mounts `useThreads` together with `useRemoteThreadLiveConnection`

Deliberate non-goal:
- no full `MainApp` test is required for Phase 6.2

## Implementation Batches
### `P6.2.a - Concurrency matrix and isolation proof`
- prove that wrong-workspace and wrong-thread events never mutate the current live connection state, active processing state, request queues, or active turn state
- keep request state scoped by workspace plus request identity
- keep turn guards authoritative so stale `completed`, `error`, and interrupt follow-up paths are no-ops

### `P6.2.b - Reconnect and guarded-refresh hardening`
- keep reconnect keyed by desired subscription, active subscription, and sequence
- stale reconnect attempts must not resubscribe, win focus recovery, or flip connection state after blur, switch, or newer recovery
- `refreshThread` remains recovery-only and must not become a second live authority
- manual refresh, detached recovery, and connected recovery must converge through the same durable thread state and live subscription rules

### `P6.2.c - Replay fidelity across refresh, reload, and restart`
- prove that resume and refresh hydration reconstruct the same semantic state for:
  - items
  - processing state
  - active turn
  - review state
  - pending requests
- preserve the current ambiguity guard:
  - local optimistic processing may survive only while remote state is ambiguous
  - once refresh or resume yields confident idle or active-turn state, durable snapshot wins
- reload and restart proof must use the same resume or hydration path rather than a memory-only reconstruction path

## Validation Requirements
Required scenario groups:
- mixed workspace events do not affect the wrong active workspace
- mixed thread events do not flip live state, active turn, requests, or processing for another thread
- approval and user-input request state does not leak across thread switches
- pending interrupt on thread A never targets thread B
- wrong-turn `completed` or `error` events remain ignored when the active turn has moved on
- blur, focus, detach, attach, `codex/connected`, and thread-switch races converge to one valid live subscription
- same-key reconnect coalesces and stale reconnect attempts clean themselves up
- manual refresh calls `refreshThread` then reconnect recovery once and remains recovery-only
- refresh and resume overlap preserves semantics with no wrong merge or state downgrade
- reload and restart rebuild the same semantic thread state from durable snapshot or resume data
- memory-only live state never overrides confident durable replay state

## Assumptions
- Durable normalized state remains the replay authority.
- Guarded refresh and live reconnect remain transient recovery aids only.
- Phase 6.2 does not absorb performance work from `6.1` or cleanup work from `6.3`.
