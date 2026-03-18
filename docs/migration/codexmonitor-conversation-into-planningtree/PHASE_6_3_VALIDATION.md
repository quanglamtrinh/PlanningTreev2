# Phase 6.3 Validation

## Gate Checklist
- [x] `P6.3-G1` cleanup inventory and classifications locked in `PHASE_6_CLEANUP_LOG.md`
- [x] `P6.3-G2` execution visible fallback removed and replacement path validated
- [x] `P6.3-G3` ask visible fallback removed while packet/reset sidecar remains functional
- [x] `P6.3-G4` breadcrumb planning visible fallback removed while graph/split planning path remains functional
- [x] `P6.3-G5` route absence, repository search, and import-ban validation pass
- [x] `P6.3-G6` docs, cleanup log, batch board, and umbrella phase trackers all agree on closure

## Proving Tests And Checks
### Frontend
- `tests/unit/ChatPanel.test.tsx`
- `tests/unit/AskPanel.test.tsx`
- `tests/unit/PlanningPanel.test.tsx`
- `tests/unit/BreadcrumbWorkspace.test.tsx`
- `tests/unit/ask-store.test.ts`
- `tests/unit/ask-sidecar-stream.test.tsx`
- `tests/unit/ConversationSurface.test.tsx`
- `tests/unit/GraphWorkspace.test.tsx`
- `tests/unit/execution-conversation-stream.test.tsx`
- `tests/unit/planning-conversation-stream.test.tsx`
- `tests/unit/ask-conversation-stream.test.tsx`
- `tests/unit/useConversationRequests.test.ts`

### Backend
- `backend/tests/integration/test_chat_api.py`
- `backend/tests/integration/test_confirmation_endpoints.py`
- `backend/tests/integration/test_conversation_gateway_api.py`
- `backend/tests/unit/test_conversation_broker.py`

### Search / Import-Ban
- `scripts/check_phase6_3_cleanup.py`

## Commands Run
### Frontend targeted cleanup and preservation suite
```bash
npx vitest run tests/unit/ChatPanel.test.tsx tests/unit/AskPanel.test.tsx tests/unit/PlanningPanel.test.tsx tests/unit/BreadcrumbWorkspace.test.tsx tests/unit/ask-store.test.ts tests/unit/ask-sidecar-stream.test.tsx tests/unit/ConversationSurface.test.tsx tests/unit/GraphWorkspace.test.tsx tests/unit/execution-conversation-stream.test.tsx tests/unit/planning-conversation-stream.test.tsx tests/unit/ask-conversation-stream.test.tsx tests/unit/useConversationRequests.test.ts
```
Result: `12` files passed, `77` tests passed.

### Backend targeted cleanup and gateway suite
```bash
python -m pytest backend/tests/integration/test_chat_api.py backend/tests/integration/test_confirmation_endpoints.py backend/tests/integration/test_conversation_gateway_api.py backend/tests/unit/test_conversation_broker.py
```
Result: `32` tests passed.

### Cleanup search/import-ban
```bash
npm run check:phase6_3_cleanup
```
Result: passed.

### Frontend typecheck
```bash
npm run typecheck
```
Result: passed.

### Frontend build
```bash
npm run build
```
Result: passed.

## Repository Search Evidence
- Runtime code no longer contains live callers for removed execution/ask/planning breadcrumb fallback symbols
- Runtime code no longer contains the retired conversation-v2 feature flags
- Preserved boundaries remain present:
  - `DeltaContextCard`
  - `useAskSidecarStream` in `BreadcrumbWorkspace`
  - `usePlanningEventStream` in `GraphWorkspace`
  - `planningHistoryByNode` in `project-store.ts`

## Non-Blocking Warnings Observed
- React `act(...)` warnings were emitted by `GraphWorkspace.test.tsx` and `ConversationSurface.test.tsx`
- React Router future-flag warnings appeared in `BreadcrumbWorkspace.test.tsx`
- `vite build` emitted a chunk-size advisory for the frontend main bundle

These warnings were recorded but did not block Phase 6.3 because all targeted assertions and commands succeeded.
