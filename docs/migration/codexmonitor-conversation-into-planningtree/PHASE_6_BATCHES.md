# Phase 6 Batches

## Sequencing Rules
- Keep the target runnable after every batch.
- Keep batch IDs stable once work starts.
- Use subphase-prefixed batch IDs only:
  - `P6.1.*`
  - `P6.2.*`
  - `P6.3.*`
- Do not claim optimization wins without recorded baseline evidence.
- Do not remove compatibility behavior without named gate evidence.

## Phase 6.1 - Performance And Dense-Event Hardening

### Pre-optimization gating
- `P6.1.b` and `P6.1.c` stay blocked until:
  - `P6.1-G1` baseline evidence is recorded for the scoped path classes
  - `P6.1-G2` dense-event corpus and expected semantic outcomes are locked
- the dense-event corpus is a semantic prerequisite for optimization, not a substitute for the bounded implementation batches below

## P6.1.a
- Title: Baseline capture and hotspot inventory
- Status: Complete
- Objective:
  - capture baseline evidence for all Phase 6.1 scoped path classes and confirm actual hotspots before optimization
- Exact scope:
  - snapshot load and hydrate baseline
  - live event fanout and parsing baseline
  - reducer state application baseline
  - normalization and merge baseline
  - transcript render baseline for long mixed conversations
  - hotspot inventory by measured cost
- Implementation notes:
  - use the same migrated path category for before/after comparisons
  - record scenario name, harness or command, and environment notes with every baseline
  - while this batch is active, lock the dense-event corpus inputs and expected semantic checks needed for `P6.1-G2`
- Done criteria:
  - baseline evidence exists and can anchor `P6.1-G1`
  - dense-event corpus definition work is documented well enough to unblock `P6.1-G2`
  - completed via:
    - `src/test/phase6_1DenseEventCorpus.ts`
    - `scripts/phase6_1_dense_event_benchmark.ts`
    - `PHASE_6_1_VALIDATION.md`

## P6.1.b
- Title: Event ingress and reducer hardening
- Status: Complete
- Objective:
  - optimize confirmed event-ingress and reducer hot paths without semantic drift
- Exact scope:
  - event fanout and listener dispatch overhead
  - app-server event parse and route overhead
  - repeated reducer work under dense streams
  - repeated normalization and preparation on partial updates
  - merge and upsert cost on long mixed transcripts
- Implementation notes:
  - comparison anchors:
    - `src/services/events.ts`
    - `src/features/app/hooks/useAppServerEvents.ts`
    - `src/features/threads/hooks/useThreadsReducer.ts`
    - `src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
    - `src/utils/threadItems.ts`
  - keep reducer semantics identical under dense streams
- Done criteria:
  - event-ingress optimizations satisfy `P6.1-G3`
  - reducer and normalization optimizations satisfy `P6.1-G4`
  - completed via:
    - `src/features/app/hooks/appServerEventRouter.ts`
    - `src/features/app/hooks/useAppServerEvents.ts`
    - `src/utils/threadItems.ts`
    - `src/features/threads/hooks/useThreadActions.ts`
    - `src/features/threads/hooks/threadReducer/threadItemsSlice.test.ts`

## P6.1.c
- Title: Render and long-transcript hardening
- Status: Complete
- Objective:
  - optimize render-model and long-transcript hot paths without semantic drift
- Exact scope:
  - render-model generation
  - transcript rendering cost
  - long-transcript grouping and expansion state
  - derived render metadata on mixed conversations
- Implementation notes:
  - comparison anchors:
    - `src/features/messages/components/Messages.tsx`
    - `src/features/messages/utils/messageRenderUtils.ts`
    - `src/utils/threadItems.ts`
  - no batching, memoization, truncation, or virtualization may change semantic outcome
- Done criteria:
  - render-path optimizations satisfy `P6.1-G5`
  - end-to-end dense-event validation satisfies `P6.1-G6`
  - completed via:
    - `src/features/messages/utils/messageRenderUtils.ts`
    - `src/features/messages/components/Messages.tsx`
    - `src/test/phase6_1DenseEventValidation.test.ts`
    - `PHASE_6_1_VALIDATION.md`

## Phase 6.2 - Concurrency, Reconnect, And Replay Robustness

## P6.2.a
- Title: Concurrency matrix and isolation proof
- Status: Complete
- Objective:
  - prove isolation across threads, conversations, and hosts
- Exact scope:
  - wrong-stream prevention
  - wrong-thread attachment prevention
  - cross-cancel prevention
  - cross-request leakage prevention
- Implementation notes:
  - prove isolation, not just absence of crashes
- Done criteria:
  - concurrency matrix exists and isolation checks pass for scoped scenarios
  - completed via:
    - `src/features/app/hooks/appServerEventRouter.test.ts`
    - `src/features/app/hooks/useAppServerEvents.test.tsx`
    - `src/features/threads/hooks/useThreadTurnEvents.test.tsx`
    - `src/features/threads/hooks/useThreadMessaging.test.tsx`
    - `src/features/threads/hooks/useThreads.integration.test.tsx`
    - `PHASE_6_2_VALIDATION.md`

## P6.2.b
- Title: Reconnect and guarded-refresh hardening
- Status: Complete
- Objective:
  - harden reconnect under detach, focus changes, missed events, and guarded refresh
- Exact scope:
  - resubscribe behavior
  - refresh recovery
  - detach recovery
  - active host switching
- Implementation notes:
  - durable replay remains authoritative
- Done criteria:
  - reconnect behavior is stress-tested and recovery-only fallbacks stay explicit
  - completed via:
    - `src/features/app/hooks/useRemoteThreadLiveConnection.ts`
    - `src/features/app/hooks/useRemoteThreadLiveConnection.test.tsx`
    - `src/test/phase6_2ConcurrencyValidation.test.tsx`
    - `PHASE_6_2_VALIDATION.md`

## P6.2.c
- Title: Replay fidelity across reload and restart
- Status: Complete
- Objective:
  - prove faithful replay after refresh, reload, and restart under stress
- Exact scope:
  - long transcript replay
  - restart recovery
  - guarded refresh convergence
- Implementation notes:
  - memory-only live state must never become replay authority
- Done criteria:
  - replay equivalence is proven on the scoped migrated paths
  - completed via:
    - `src/features/threads/hooks/useThreadActions.test.tsx`
    - `src/test/phase6_2ConcurrencyValidation.test.tsx`
    - `PHASE_6_2_VALIDATION.md`

## Phase 6.3 - Compatibility Cleanup And Gate-Based Removal

## P6.3.a
- Title: Compatibility inventory and classification
- Status: Not started
- Objective:
  - inventory transitional compatibility behavior and classify it before cleanup
- Exact scope:
  - legacy adapters
  - duplicate routing
  - shadow state
  - redundant reconnect paths
- Implementation notes:
  - every target must be classified as removable, blocked, intentionally permanent, or uncertain
- Done criteria:
  - compatibility inventory exists and `PHASE_6_CLEANUP_LOG.md` is populated with initial classifications

## P6.3.b
- Title: Gate-qualified bounded removals
- Status: Not started
- Objective:
  - remove only the compatibility behavior that has explicit gate evidence
- Exact scope:
  - bounded removals
  - replacement-path verification
  - rollback impact records
- Implementation notes:
  - no removal without named gate evidence
- Done criteria:
  - every removal is tied to a `P6.1-G*` or `P6.2-G*` gate and logged in `PHASE_6_CLEANUP_LOG.md`

## P6.3.c
- Title: Post-removal verification and permanent architecture record
- Status: Not started
- Objective:
  - verify removals and record what remains intentionally permanent
- Exact scope:
  - regression checks
  - documentation updates
  - permanent-vs-transitional record
- Implementation notes:
  - cleanup closeout must increase confidence, not reduce it
- Done criteria:
  - removed and surviving compatibility paths are explicitly documented and verified
