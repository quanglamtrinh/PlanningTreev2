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
- Done criteria:
  - baseline evidence exists and can anchor `P6.1-G1`
  - dense-event corpus definition work is documented well enough to unblock `P6.1-G2`

## P6.1.b
- Title: Event ingress and reducer hardening
- Status: Complete
- Objective:
  - optimize confirmed event-ingress and reducer hot paths without semantic drift
- Exact scope:
  - event fanout and listener dispatch overhead
  - repeated reducer work under dense streams
  - repeated normalization and preparation on partial updates
  - merge and upsert cost on long mixed transcripts
- Done criteria:
  - event-ingress optimizations satisfy `P6.1-G3`
  - reducer and normalization optimizations satisfy `P6.1-G4`

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
- Done criteria:
  - render-path optimizations satisfy `P6.1-G5`
  - end-to-end dense-event validation satisfies `P6.1-G6`

## Phase 6.2 - PlanningTreeMain Concurrency, Reconnect, And Replay Robustness

## P6.2.a
- Title: Lock the concurrency matrix and isolation rules
- Status: Complete
- Objective:
  - prove isolation across scope, conversation, stream, turn, and request ownership
- Exact scope:
  - wrong-scope no-op behavior
  - wrong-conversation no-op behavior
  - stale-seq and stale-turn no-op behavior
  - request scoping by `conversation_id + request_id`
  - broker isolation by `project_id + conversation_id`
- Completed via:
  - `frontend/src/features/conversation/model/applyConversationEvent.ts`
  - `frontend/src/stores/conversation-store.ts`
  - `backend/services/conversation_gateway.py`
  - `backend/tests/unit/test_conversation_broker.py`
  - `frontend/tests/unit/applyConversationEvent.test.ts`
  - `frontend/tests/unit/conversation-store.test.ts`
  - `backend/tests/integration/test_conversation_gateway_api.py`

## P6.2.b
- Title: Reconnect sequencing and stale-attempt suppression
- Status: Complete
- Objective:
  - make reconnect owned by current scope plus bootstrap generation and suppress stale completions
- Exact scope:
  - gap-triggered recovery
  - same-scope reconnect coherence
  - stale reconnect no-op behavior after scope switch or remount
  - buffered old-stream emission rejection
- Completed via:
  - `frontend/src/features/conversation/hooks/streamRuntime.ts`
  - `frontend/src/features/conversation/hooks/useExecutionConversation.ts`
  - `frontend/src/features/conversation/hooks/usePlanningConversation.ts`
  - `frontend/src/features/conversation/hooks/useAskConversation.ts`
  - `frontend/tests/unit/execution-conversation-stream.test.tsx`
  - `frontend/tests/unit/planning-conversation-stream.test.tsx`
  - `frontend/tests/unit/ask-conversation-stream.test.tsx`

## P6.2.c
- Title: Guarded refresh hardening
- Status: Complete
- Objective:
  - keep refresh durable-first and prevent older refresh results from overwriting newer accepted live state
- Exact scope:
  - snapshot-first reconnect
  - terminal refresh convergence
  - older refresh suppression after scope switch
  - refresh overlap with current live generation
- Completed via:
  - `frontend/src/features/conversation/hooks/streamRuntime.ts`
  - `frontend/src/features/conversation/hooks/useExecutionConversation.ts`
  - `frontend/src/features/conversation/hooks/usePlanningConversation.ts`
  - `frontend/src/features/conversation/hooks/useAskConversation.ts`
  - `frontend/src/stores/conversation-store.ts`
  - `frontend/tests/unit/planning-conversation-stream.test.tsx`
  - `frontend/tests/unit/ask-conversation-stream.test.tsx`
  - `frontend/tests/unit/conversation-store.test.ts`

## P6.2.d
- Title: Replay fidelity across refresh, reload, and restart
- Status: Complete
- Objective:
  - prove semantic equivalence after remount and durable replay
- Exact scope:
  - same visible ordering after remount
  - same pending request set after remount
  - same active stream and active turn ownership after durable recovery
  - stale old-stream emissions ignored after remount
- Completed via:
  - `frontend/tests/unit/conversation-recovery-orchestration.test.tsx`
  - `frontend/tests/unit/ConversationSurface.test.tsx`
  - `backend/tests/unit/test_conversation_gateway.py`
  - `backend/tests/unit/test_conversation_store.py`
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
- Done criteria:
  - every removal is tied to named gate evidence and logged in `PHASE_6_CLEANUP_LOG.md`

## P6.3.c
- Title: Post-removal verification and permanent architecture record
- Status: Not started
- Objective:
  - verify removals and record what remains intentionally permanent
- Exact scope:
  - regression checks
  - documentation updates
  - permanent-vs-transitional record
- Done criteria:
  - removed and surviving compatibility paths are explicitly documented and verified
