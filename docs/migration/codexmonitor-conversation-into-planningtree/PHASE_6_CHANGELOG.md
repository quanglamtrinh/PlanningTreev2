# Phase 6 Changelog

## 2026-03-17
### Phase 6.3 closeout
- Removed `backend/routes/chat.py` from the backend public route surface and replaced legacy route tests with route-absence proof
- Removed `legacyConversationAdapter.ts`, `chat-store.ts`, legacy breadcrumb panels, and visible-host feature flag fallbacks
- Made `ChatPanel`, `AskPanel`, and `PlanningPanel` conversation-v2-only host surfaces
- Narrowed `ask-store.ts` to packet/reset sidecar ownership and replaced `useAskSessionStream` with `useAskSidecarStream`
- Preserved `DeltaContextCard` packet/reset sidecar behavior and graph/split planning history behavior as explicitly out-of-scope boundaries
- Added `scripts/check_phase6_3_cleanup.py` and the root `npm run check:phase6_3_cleanup` script
- Recorded targeted frontend, backend, typecheck, build, and search/import-ban evidence for 6.3 closure

### Phase 6 final status
- `6.1` complete
- `6.2` complete
- `6.3` complete
- Phase 6 accepted with documented carry-forward items outside current cleanup scope
