# Phase 6.2 Validation

## Current Status
- Complete

## Reviewed Commit Basis
- The reviewed `PlanningTreeMain` commit `bb3f01b (chat-phase-6.2)` is docs-only per `git show --stat --name-only bb3f01b`.
- It is sufficient to show that the Phase 6.2 matrix and trackers were written, but it was not sufficient to claim runtime/test proof or gate closure beyond `P6.2-G1`.
- The actual runtime/test proof later landed in `CodexMonitor` commit `924cbd3`.

## Verification Commands
- `npm test -- src/features/app/hooks/appServerEventRouter.test.ts src/features/app/hooks/useAppServerEvents.test.tsx src/features/app/hooks/useRemoteThreadLiveConnection.test.tsx src/features/threads/hooks/useThreadTurnEvents.test.tsx src/features/threads/hooks/useThreadMessaging.test.tsx src/features/threads/hooks/useThreadActions.test.tsx src/features/threads/hooks/useThreads.integration.test.tsx src/test/phase6_2ConcurrencyValidation.test.tsx`
- `npm run typecheck`

## Gate Checklist
- [x] `P6.2-G1` concurrency, reconnect, and replay matrix is recorded
- [x] `P6.2-G2` mixed workspace, thread, turn, and request isolation is proven
- [x] `P6.2-G3` reconnect race scenarios pass with no stale attach or wrong-state flip
- [x] `P6.2-G4` guarded refresh paths are proven recovery-only
- [x] `P6.2-G5` replay fidelity after refresh, reload, and restart is proven durable-store-first
- [x] `P6.2-G6` end-to-end stress validation and docs closeout both pass

## Validation Matrix
| Trigger or scenario | Expected durable source of truth | Expected live-side behavior | Forbidden failure mode | Proving surface |
| --- | --- | --- | --- | --- |
| wrong-workspace app-server event | workspace-scoped thread state | ignore event for the active live connection | reconnecting or mutating the current workspace from another workspace's event | `appServerEventRouter.test.ts`, `phase6_2ConcurrencyValidation.test.tsx` |
| stale detach from previously active thread | currently selected thread and subscription key | ignore detach for the old thread after a switch | reattaching or refreshing the stale thread | `useRemoteThreadLiveConnection.test.tsx`, `phase6_2ConcurrencyValidation.test.tsx` |
| identical request ids across workspaces | workspace plus request identity | keep both approval and user-input requests isolated | deduping or removing requests across workspaces | `appServerEventRouter.test.ts`, `useThreads.integration.test.tsx` |
| pending interrupt and stale turn events | latest known active turn by thread | no-op on stale turn ids and other-thread interrupts | cross-cancel or wrong-turn cleanup | `useThreadTurnEvents.test.tsx`, `useThreadMessaging.test.tsx` |
| `codex/connected` while blurred | durable thread snapshot plus current focus state | do not auto-recover until foreground recovery is allowed | blur-time reconnect or stale subscription attach | `useRemoteThreadLiveConnection.test.tsx` |
| manual refresh recovery | forced durable refresh followed by reconnect | refresh first, reconnect second, no second live authority | reconnect winning before refresh or refresh becoming a parallel live source | `phase6_2ConcurrencyValidation.test.tsx` |
| reload or restart remount | resumed durable thread snapshot | rebuild the same semantic items, processing state, review state, and active turn | memory-only replay drift after remount | `phase6_2ConcurrencyValidation.test.tsx`, `useThreadActions.test.tsx` |

## Scenario Coverage
- [x] mixed workspace events do not affect the wrong active workspace
- [x] mixed thread events do not flip live state, active turn, requests, or processing for another thread
- [x] approval and user-input request state does not leak across thread switches
- [x] pending interrupt on thread A never targets thread B
- [x] wrong-turn `completed` or `error` events remain ignored when the active turn has moved on
- [x] blur, focus, detach, attach, `codex/connected`, and thread-switch races converge to one valid live subscription
- [x] same-key reconnect coalesces and stale reconnect attempts clean themselves up
- [x] manual refresh calls `refreshThread` then reconnect recovery once and remains recovery-only
- [x] refresh and resume overlap preserves semantics with no wrong merge or state downgrade
- [x] reload and restart rebuild the same semantic thread state from durable snapshot or resume data
- [x] memory-only live state never overrides confident durable replay state

## Notes
- The proof patch for these checks is `924cbd3`.
- `useThreads.integration.test.tsx` still emits pre-existing React `act(...)` warnings in older scenarios, but the targeted 6.2 assertions pass and those warnings did not indicate semantic drift in the new 6.2 coverage.
