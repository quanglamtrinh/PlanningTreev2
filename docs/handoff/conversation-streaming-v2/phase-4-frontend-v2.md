# Phase 4: Frontend V2 Hidden Breadcrumb Surface

Status: completed.

## Goal

Land a hidden `/chat-v2` breadcrumb surface that talks to the V2 conversation backend end to end while leaving the default `/chat` V1 route untouched.

Phase 4 is successful only if the hidden path behaves like a real breadcrumb surface, not just a conversation demo.

## Rollout Shape

- hidden route: `/projects/:projectId/nodes/:nodeId/chat-v2`
- default user-facing breadcrumb route stays on `/chat`
- conversation transport is V2-only on the hidden path
- detail-state loading, workflow refresh fallback, and local-review acceptance remain on current detail APIs
- V1 chat store and semantic mapper remain untouched for the default route during this phase

## Required Parity With V1 Breadcrumb Flow

### Route and shell parity

- `Layout` must treat both `/chat` and `/chat-v2` as breadcrumb routes for Back-to-Graph behavior
- `BreadcrumbPlaceholderV2` must set `activeSurface("breadcrumb")`
- route-local redirects inside the hidden path must stay on `/chat-v2`
- review nodes must force the audit thread and hide the detail pane
- non-review nodes must keep the thread pane plus detail pane layout

### Route-to-project parity

- route project and node ids must stay synchronized with `useProjectStore`
- route node must sync through `useProjectStore.selectNode(nodeId, false)`
- `loadDetailState(projectId, nodeId)` and V2 `loadThread(projectId, nodeId, threadRole)` must begin in parallel once route identity is resolved
- V2 thread load must not wait on detail-state completion

### Breadcrumb content parity

- ask and audit on non-review nodes must keep the `FrameContextFeedBlock` prefix
- review nodes must render the solo audit layout
- composer read-only gating must follow current detail-state rules

### Audit acceptance parity

- hidden V2 must support the local-review acceptance bar on the audit tab
- acceptance still uses `useDetailStateStore.acceptLocalReview(...)`
- success path must reset local `threadTab` to `ask`
- success path must navigate to the activated sibling on `/chat-v2`

### Reset parity

- reset UI lives in the hidden thread header, not the composer
- reset is available only for `ask_planning`
- reset visibility or enablement must match backend writability
- hidden path must converge reset through `thread.reset` plus `thread.snapshot`, not through POST body replacement

## Implementation Scope

### V2 transport layer

- extend `frontend/src/api/types.ts` with a separate V2 conversation type surface
- extend `frontend/src/api/client.ts` with V2-only helpers
- keep V1 `jsonFetch()` semantics unchanged
- add a V2-only unwrap layer for `{ ok, data }` envelopes
- ensure every V2 EventSource URL passes through `appendAuthToken()`

### V2 conversation state

- add `frontend/src/features/conversation/state/threadStoreV2.ts`
- add `frontend/src/features/conversation/state/applyThreadEvent.ts`
- add `frontend/src/features/conversation/state/threadEventRouter.ts`
- add `frontend/src/features/conversation/state/workflowEventBridge.ts`
- keep `frontend/src/stores/chat-store.ts` unchanged

Required state rules:

- only `conversation.item.upsert` and `conversation.item.patch` mutate `snapshot.items`
- requested and resolved companion events mutate pending-request state only
- patching a missing item is a mismatch path, not an implicit upsert
- `outputFilesReplace` overwrites any preview accumulated from `outputFilesAppend`
- no pair-based message logic exists anywhere in V2

### Stale-request and stale-SSE guards

The V2 store must keep an explicit generation-token guard equivalent to the V1 `sessionGeneration + isActiveTarget` pattern.

Required guard behavior:

- route change, tab change, or disconnect invalidates pending completions
- every load, send, reset, reconnect, and stream handler checks both generation and active `(projectId, nodeId, threadRole)`
- stale snapshot responses must be ignored
- stale SSE events must be ignored
- reconnect timers must re-check generation before reopening

### Rendering

- add render-by-kind components under `frontend/src/features/conversation/components/`
- render directly from canonical `ConversationItem[]`
- do not use `semanticMapper.ts` or `SemanticBlocks.tsx` on the hidden path
- working indicator derives from `processingState + activeTurnId`

## Landed Summary

The following Phase 4 slices are landed and treated as complete for rollout purposes:

- hidden `/chat-v2` route in `frontend/src/App.tsx`
- breadcrumb route parity in `frontend/src/components/Layout.tsx`
- separate V2 placeholder and breadcrumb view
- V2 API types and V2 client helpers
- separate V2 Zustand store and event applier
- explicit generation-token stale guards in the V2 store
- direct render-by-kind conversation components
- header reset action on the hidden ask thread
- local-review acceptance parity on `/chat-v2`
- project-global V2 workflow bridge hook
- focused unit and route tests for the new path

Phase 4 is closed as a hidden-rollout frontend phase. `/chat-v2` is now the rehearsal surface for Phase 5, while `/chat` remains the default V1 route.

## File Targets

- `frontend/src/App.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/conversation/BreadcrumbPlaceholderV2.tsx`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
- `frontend/src/features/conversation/state/*`
- `frontend/src/features/conversation/components/*`
- `frontend/tests/unit/applyThreadEvent.test.ts`
- `frontend/tests/unit/threadStoreV2.test.ts`
- `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- `frontend/tests/unit/Layout.test.tsx`

## Final Verification

Required verification for this phase was:

- reducer tests for snapshot, upsert, patch, missing-item mismatch, and `outputFilesReplace`
- store tests for load, send, stale-load ignore, and stream wiring
- route tests for `/chat-v2` shell parity and local-review navigation
- V1 regression tests for `Layout`, `BreadcrumbChatView`, and `chat-store`
- frontend `typecheck`

Focused verification completed on 2026-03-28:

- `npm run typecheck`
- `npx vitest run tests/unit/applyThreadEvent.test.ts tests/unit/threadStoreV2.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx tests/unit/Layout.test.tsx tests/unit/BreadcrumbChatView.test.tsx tests/unit/chat-store.test.ts`

Results:

- frontend typecheck passed
- focused V2 + V1 regression suite passed: 6 files, 47 tests
- full frontend unit suite failed in exactly one unrelated legacy detail-panel test:
  - `tests/unit/NodeDetailCard.test.tsx > NodeDetailCard > shows execution lifecycle badge separately from coarse node status`
  - failing assertion expects `Execution Complete`

Blocker triage disposition:

- the failure reproduces entirely inside the legacy `NodeDetailCard` graph/detail path
- the failing DOM does not involve hidden `/chat-v2`, V2 conversation items, or V2 store/router code
- `frontend/src/features/node/NodeDetailCard.tsx` does not depend on the V2 conversation stack
- this is treated as unrelated baseline noise and is waived for Phase 4 closeout

Smoke evidence:

- executable route/view evidence is recorded in `tests/unit/BreadcrumbChatViewV2.test.tsx`, `tests/unit/Layout.test.tsx`, and `tests/unit/threadStoreV2.test.ts`
- supporting notes, route-access instructions, and checklist coverage are recorded in `docs/handoff/conversation-streaming-v2/artifacts/phase-4/smoke-checklist.md`

## Exit Criteria

- hidden `/chat-v2` exists and behaves like a breadcrumb surface
- V2 conversation path renders only from canonical items
- V2 conversation path does not depend on pair-based semantics or semantic mapping
- stale-response and stale-SSE guards are implemented
- reset-thread UI exists on hidden ask-planning path and converges through SSE or explicit reload
- local-review acceptance parity is preserved on `/chat-v2`
- V1 route remains isolated and unchanged by default

All exit criteria above are satisfied for Phase 4 closeout.

## Phase 5 Handoff

Phase 5 can assume:

- `/chat-v2` is the rehearsal frontend surface
- conversation transport is V2-only on the hidden path
- detail-state loading and local-review acceptance remain side-channel by design at this phase boundary
- no additional Phase 4 feature work is expected unless rehearsal finds a real parity regression

## Artifacts To Produce

- `docs/handoff/conversation-streaming-v2/artifacts/phase-4/README.md`
- `docs/handoff/conversation-streaming-v2/artifacts/phase-4/implementation-notes.md`
- `docs/handoff/conversation-streaming-v2/artifacts/phase-4/verification-notes.md`
- `docs/handoff/conversation-streaming-v2/artifacts/phase-4/smoke-checklist.md`
