# Phase 6.2 Plan: PlanningTreeMain Concurrency, Reconnect, And Replay Robustness

## Inheritance
- This subphase inherits all Phase 6 entry conditions, invariants, gate rules, and cleanup boundaries from `PHASE_6_PLAN.md`.
- It narrows Phase 6 to isolation, reconnect correctness, guarded refresh behavior, and replay robustness only.
- It does not introduce new conversation semantics, new product flows, or cleanup removals.

## Summary
- Phase 6.2 hardens the migrated conversation-v2 path in `PlanningTreeMain` under concurrent activity and recovery stress.
- `PlanningTreeMain` uses the native identity model for this phase:
  - scope key = `project_id + node_id + thread_type`
  - conversation ownership = `conversation_id`
  - live stream ownership = `conversation_id + active_stream_id`
  - turn ownership = `conversation_id + turn_id`
  - request ownership = `conversation_id + request_id`
  - replay ordering = durable `event_seq`
- Completion note:
  - this plan is now implemented in `PlanningTreeMain`
  - closeout evidence is recorded in `PHASE_6_2_VALIDATION.md`

## Scope
- concurrent live-event isolation across scope, conversation, stream, turn, and request boundaries
- reconnect sequencing, coalescing, and stale-attempt suppression
- guarded refresh behavior
- replay fidelity after refresh, remount, reload, and restart

## Out Of Scope
- new message semantics
- new action semantics
- new lineage rules
- cleanup and compatibility removals
- shell migration
- architecture rewrites that are not required to prove isolation or replay correctness

## Canonical Definitions And Acceptance Rules
- `bootstrap generation` = a monotonically increasing token incremented on scope mount, remount, or refresh-authority reset; completions from older generations are no-ops
- `confident durable truth` = a snapshot or refresh result that establishes current `conversation_id`, baseline `event_seq`, and ownership fields needed to accept or reject live events
- `same semantic state` = equality of visible message order, visible part order, conversation status, active stream ownership, active turn ownership, pending request identities and statuses, and review/passive projections already defined by earlier phases
- buffered SSE events may flush only when they still match the current scope key, current `conversation_id`, current bootstrap generation, and the canonical acceptance rules below

Canonical live-event classes:
- stream-owned live events = the current SSE runtime events applied through `applyConversationEvent.ts`; they require a valid `stream_id` and must satisfy active-stream ownership
- conversation-owned stream-agnostic live events = none by default in Phase 6.2; do not introduce a new stream-agnostic live event family here
- durable refresh authority = snapshot or refresh responses from the conversation API; these may rebase durable state, but they are not a parallel live stream

Canonical event acceptance rules:
- incoming live events must match the current scope key and current `conversation_id`
- `event_seq <= current event_seq` is a no-op
- the next contiguous `event_seq` may apply only if ownership guards pass
- a gapful `event_seq` must not be synthesized locally; it triggers guarded recovery or refresh
- events requiring stream ownership must match the current `active_stream_id`
- stale turn terminal events are no-ops if `turn_id` no longer owns active-turn state
- request events are scoped by `conversation_id + request_id`; stale resolution or cleanup from superseded turns or superseded stream ownership may not mutate the current pending-request map unless ownership still matches
- a refresh result may not overwrite newer accepted live state if that refresh was started from an older bootstrap generation or older baseline `event_seq`
- durable snapshot or refresh output wins once it establishes current `conversation_id`, baseline `event_seq`, and ownership fields needed for acceptance

## Exit Gates
### `P6.2-G1` - Concurrency And Replay Matrix Locked
- A single validation matrix exists and is treated as the semantic ground truth for this phase.
- The matrix covers:
  - scope key
  - `conversation_id`
  - `active_stream_id`
  - `turn_id`
  - `request_id`
  - durable `event_seq`
  - recovery trigger

### `P6.2-G2` - Isolation Is Proven
- wrong-scope, wrong-conversation, stale-turn, stale-request, and stale-stream events are explicit no-ops
- publish/subscribe and snapshot reload stay conversation-scoped
- same `request_id` values remain isolated by `conversation_id`

### `P6.2-G3` - Reconnect Hardening Is Proven
- reconnect attempts are owned by the current scope key plus bootstrap generation
- stale reconnect completions may not revive an old scope, old `conversation_id`, or old `active_stream_id`
- old EventSource instances may not flush buffered events after unmount, remount, scope switch, or newer reconnect generation

### `P6.2-G4` - Guarded Refresh Is Recovery-Only
- refresh loads snapshot state first, then reopens or continues SSE only if refreshed ownership still allows it
- refresh may rebase durable state, but may not independently publish a competing live ownership state outside the current bootstrap generation
- old refresh results from older generations or older baselines are no-ops

### `P6.2-G5` - Replay Fidelity Is Proven
- snapshot hydration plus accepted events remain the only replay authority
- optimistic local state survives only while durable truth is ambiguous
- refresh, remount, reload, and restart rebuild the same semantic state

### `P6.2-G6` - Stress Validation And Closeout Pass
- targeted frontend and backend validation passes
- `npm run typecheck` passes
- frontend build passes
- 6.2 docs, gate board, and open-issue state agree with the proof surfaces

## Source Context Anchors
- `frontend/src/features/conversation/model/applyConversationEvent.ts`
- `frontend/src/stores/conversation-store.ts`
- `frontend/src/features/conversation/hooks/streamRuntime.ts`
- `frontend/src/features/conversation/hooks/useExecutionConversation.ts`
- `frontend/src/features/conversation/hooks/usePlanningConversation.ts`
- `frontend/src/features/conversation/hooks/useAskConversation.ts`
- `backend/services/conversation_gateway.py`
- `backend/streaming/conversation_broker.py`
- `backend/storage/conversation_store.py`

## Proof Model
### Layer 1 - Pure Routing And Guard Logic
- prove that wrong-scope, stale-seq, stale-stream, stale-turn, and stale-request events are rejected before mutating state

### Layer 2 - Hook-Level Concurrency Semantics
- prove that execution, planning, and ask hooks keep ownership scoped to the mounted scope and current generation

### Layer 3 - Recovery Sequencing
- prove that reconnect, refresh, and resume paths converge to one valid outcome even when triggers overlap

### Layer 4 - Orchestration-Level Semantic Replay
- prove that remounting the conversation host reconstructs the same semantic state from durable data and rejects stale buffered emissions from an old stream

## Implementation Batches
### `P6.2.a` - Lock The Concurrency Matrix And Isolation Rules
- implemented through:
  - `frontend/src/features/conversation/model/applyConversationEvent.ts`
  - `frontend/src/stores/conversation-store.ts`
  - `backend/services/conversation_gateway.py`
  - `backend/tests/unit/test_conversation_broker.py`
  - `frontend/tests/unit/applyConversationEvent.test.ts`
  - `frontend/tests/unit/conversation-store.test.ts`
  - `backend/tests/integration/test_conversation_gateway_api.py`

### `P6.2.b` - Reconnect Sequencing And Stale-Attempt Suppression
- implemented through:
  - `frontend/src/features/conversation/hooks/streamRuntime.ts`
  - `frontend/src/features/conversation/hooks/useExecutionConversation.ts`
  - `frontend/src/features/conversation/hooks/usePlanningConversation.ts`
  - `frontend/src/features/conversation/hooks/useAskConversation.ts`
  - `frontend/tests/unit/execution-conversation-stream.test.tsx`
  - `frontend/tests/unit/planning-conversation-stream.test.tsx`
  - `frontend/tests/unit/ask-conversation-stream.test.tsx`

### `P6.2.c` - Guarded Refresh Hardening
- implemented through:
  - the same hook surfaces as `P6.2.b`
  - older-refresh suppression and snapshot-first reconnect rules in the stream tests
  - durable-first request resolution scoping in `backend/services/conversation_gateway.py`

### `P6.2.d` - Replay Fidelity Across Refresh, Reload, And Restart
- implemented through:
  - `frontend/tests/unit/conversation-recovery-orchestration.test.tsx`
  - `frontend/tests/unit/ConversationSurface.test.tsx`
  - `backend/tests/unit/test_conversation_gateway.py`
  - `backend/tests/unit/test_conversation_store.py`

## Required Validation Commands
- frontend:
  - `npm run test:unit -- execution-conversation-stream.test.tsx planning-conversation-stream.test.tsx ask-conversation-stream.test.tsx conversation-store.test.ts applyConversationEvent.test.ts ConversationSurface.test.tsx useConversationRequests.test.ts conversation-recovery-orchestration.test.tsx`
  - `npm run typecheck`
  - `npm run build`
- backend:
  - `python -m pytest backend/tests/unit/test_conversation_gateway.py backend/tests/unit/test_conversation_broker.py backend/tests/unit/test_conversation_store.py backend/tests/integration/test_conversation_gateway_api.py`

## Deliverables
- `PHASE_6_2_PLAN.md`
- `PHASE_6_2_PROGRESS.md`
- `PHASE_6_2_VALIDATION.md`
- `PHASE_6_2_OPEN_ISSUES.md`
- `PHASE_6_PROGRESS.md`
- `PHASE_6_OPEN_ISSUES.md`
- `PHASE_6_BATCHES.md`
- `PHASE_6_CHANGELOG.md`

## Assumptions
- `PlanningTreeMain` is the implementation target; CodexMonitor is source context only.
- durable normalized state remains the replay authority
- earlier semantic phases already define the meaning being replayed
- cleanup and compatibility removal remain exclusive to Phase 6.3
