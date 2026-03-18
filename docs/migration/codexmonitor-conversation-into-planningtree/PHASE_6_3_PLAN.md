# Phase 6.3 Plan: PlanningTreeMain Compatibility Cleanup And Gate-Based Removal

## Status
Complete on `PlanningTreeMain`.

Phase 6.3 was executed as a bounded cleanup phase only. It removed transitional compatibility surfaces that no longer owned the visible conversation-v2 host path, preserved explicitly out-of-scope compatibility boundaries, and did not introduce new semantics, new product flows, or cleanup-by-refactor.

## Locked Decisions
- Target repo: `PlanningTreeMain`
- Cleanup strategy: bounded slices, not big-bang
- Ask cleanup: included for visible transcript/session fallback only
- Graph/split planning cleanup: not included beyond breadcrumb-visible fallback removal
- Flag retirement rule: flags are retired only after their guarded fallback branches are physically removed
- Classification vocabulary: `transitional_and_removable`, `transitional_but_blocked`, `preserved_out_of_scope_for_6_3`, `uncertain_requires_decision`

## Scope That Landed
- Removed execution visible legacy fallback from the breadcrumb host path
- Removed ask visible legacy transcript/session fallback while preserving packet/reset sidecar behavior
- Removed breadcrumb-visible planning fallback while preserving graph/split planning history behavior
- Removed the retired execution v1 chat route family from backend route registration
- Added cleanup validation for removed symbols/paths and preserved graph/sidecar boundaries

## Preserved Boundaries
- Ask packet/reset sidecar remains `preserved_out_of_scope_for_6_3`
- Ask reset ownership remains `transitional_but_blocked`
- Graph/split planning history path remains `preserved_out_of_scope_for_6_3`

These preserved boundaries are not permanent architecture claims. They are intentionally retained boundaries that require a later dedicated cleanup or redesign phase.

## Canonical Removal Rules
A compatibility surface may be removed only when all of the following are true:
- the replacement path is already the default validated path
- no preserved boundary still depends on the surface
- rollback confidence is not materially reduced
- repository search proves no live caller remains
- targeted tests prove preserved paths still work after cleanup

Additional rules used in this closeout:
- preserved boundaries must be listed explicitly with rationale
- route removal requires repository search, API validation, and backend caller audit
- feature flags may be retired only after guarded fallback branches are physically removed
- for this repo state, the retired conversation-v2 flags were verified to be referenced only from `BreadcrumbWorkspace` before deletion

## Implemented Batches
### P6.3.a - Inventory, Classification, And Audit
- Seeded `PHASE_6_CLEANUP_LOG.md` with `P6.3-R1` through `P6.3-R9`
- Audited callers for legacy breadcrumb panels, legacy stores, legacy stream hooks, the retired v1 chat route family, and preserved graph/ask boundaries

### P6.3.b - Remove Dead Adapter And Execution Compatibility
- Removed `legacyConversationAdapter.ts`
- Made `ChatPanel` conversation-v2-only and removed `LegacyExecutionChatPanel`
- Removed visible execution ownership from `chat-store.ts`
- Removed `useChatSessionStream` and retired execution v1 client helpers
- Removed `backend/routes/chat.py` from the backend public route surface
- Retired the execution conversation-v2 feature flag fallback

### P6.3.c - Remove Ask Legacy Transcript/Session Fallback, Preserve Sidecar
- Made `AskPanel` conversation-v2-only and removed `LegacyAskPanel`
- Narrowed `ask-store.ts` to packet/reset sidecar ownership only
- Replaced `useAskSessionStream` with `useAskSidecarStream`
- Retired the ask conversation-v2 feature flag fallback
- Preserved packet routes, packet event handling, and reset-adjacent behavior required by `DeltaContextCard`

### P6.3.d - Remove Breadcrumb Planning Fallback, Preserve Graph/Split Planning
- Made `PlanningPanel` conversation-v2-only and removed `LegacyPlanningPanel`
- Removed breadcrumb-visible planning fallback from `BreadcrumbWorkspace`
- Preserved `GraphWorkspace`, `usePlanningEventStream`, `project-store.planningHistoryByNode`, and split/planning history backend routes
- Retired the planning conversation-v2 feature flag fallback after confirming no remaining callers

### P6.3.e - Closeout, Import Bans, And Permanent Record
- Added `scripts/check_phase6_3_cleanup.py`
- Added root script `npm run check:phase6_3_cleanup`
- Added backend route-absence proof for retired execution v1 chat routes
- Updated Phase 6.3 docs and umbrella trackers to reflect final cleanup state

## Gate Outcome
- `P6.3-G1` cleanup inventory and classifications locked: complete
- `P6.3-G2` execution visible fallback removed: complete
- `P6.3-G3` ask visible fallback removed while sidecar preserved: complete
- `P6.3-G4` breadcrumb planning visible fallback removed while graph/split planning preserved: complete
- `P6.3-G5` route absence plus import-ban validation pass: complete
- `P6.3-G6` docs, validation commands, cleanup log, and umbrella trackers agree: complete

## Proof Surfaces
- Frontend host cleanup: `ChatPanel.test.tsx`, `AskPanel.test.tsx`, `PlanningPanel.test.tsx`, `BreadcrumbWorkspace.test.tsx`
- Ask sidecar proof: `ask-store.test.ts`, `ask-sidecar-stream.test.tsx`, `AskPanel.test.tsx`
- Preserved graph path proof: `GraphWorkspace.test.tsx`, `planning-conversation-stream.test.tsx`
- Conversation-v2 host/path proof: `execution-conversation-stream.test.tsx`, `ask-conversation-stream.test.tsx`, `ConversationSurface.test.tsx`, `useConversationRequests.test.ts`
- Backend route and gateway proof: `test_chat_api.py`, `test_confirmation_endpoints.py`, `test_conversation_gateway_api.py`, `test_conversation_broker.py`
- Search/import-ban proof: `scripts/check_phase6_3_cleanup.py`

## Closeout Commands
- `npx vitest run tests/unit/ChatPanel.test.tsx tests/unit/AskPanel.test.tsx tests/unit/PlanningPanel.test.tsx tests/unit/BreadcrumbWorkspace.test.tsx tests/unit/ask-store.test.ts tests/unit/ask-sidecar-stream.test.tsx tests/unit/ConversationSurface.test.tsx tests/unit/GraphWorkspace.test.tsx tests/unit/execution-conversation-stream.test.tsx tests/unit/planning-conversation-stream.test.tsx tests/unit/ask-conversation-stream.test.tsx tests/unit/useConversationRequests.test.ts`
- `python -m pytest backend/tests/integration/test_chat_api.py backend/tests/integration/test_confirmation_endpoints.py backend/tests/integration/test_conversation_gateway_api.py backend/tests/unit/test_conversation_broker.py`
- `npm run check:phase6_3_cleanup`
- `npm run typecheck`
- `npm run build`

## Non-Blocking Notes
- The targeted frontend run still emits pre-existing React `act(...)` warnings in `GraphWorkspace.test.tsx` and `ConversationSurface.test.tsx`
- `vite build` emits a chunk-size advisory for the main bundle
- Neither warning blocked 6.3 acceptance because assertions passed and cleanup invariants held
