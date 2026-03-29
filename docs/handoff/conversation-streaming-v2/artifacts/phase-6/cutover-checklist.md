# Phase 6 Cutover Checklist

## Backend

- [x] dedicated production flag added: `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`
- [x] execution production path branches to V2 runtime
- [x] review-rollup production path branches to V2 runtime
- [x] auto-review production transcript path branches to V2 runtime
- [x] legacy transcript events are suppressed on production V2 execution and audit paths
- [x] workflow invalidate events still emit for execution, auto-review, and rollup milestones
- [ ] `item/commandExecution/terminalInteraction` projects into canonical tool output
- [ ] backend integration coverage proves terminal interaction appears in the V2 feed

## Frontend

- [x] `/chat` redirects execution and audit selections to `/chat-v2`
- [x] `/chat-v2` redirects ask traffic back to `/chat`
- [x] graph finish-task entry opens `/chat-v2?thread=execution`
- [x] review-node breadcrumb entry opens `/chat-v2?thread=audit`
- [x] sidebar review-node entry opens `/chat-v2?thread=audit`

## Semantic Presentation Parity

- [ ] add `useConversationViewState.ts` for grouped entries, expansion state, and auto-scroll semantics
- [ ] replace flat `items.map(...)` feed rendering with grouped execution or audit presentation
- [ ] derive `latestReasoningLabel` from visible reasoning items
- [ ] upgrade `WorkingIndicator` to show semantic progress and timing
- [ ] add tool-group collapse and expand behavior
- [ ] add live command-output viewport behavior for command tools
- [ ] stop unconditional scroll-to-bottom on every item or lifecycle change
- [ ] verify `outputFilesReplace` still wins over preview entries after grouping changes

## Verification

- [x] targeted backend unit suite passes
- [x] dedicated Phase 6 production integration test passes
- [x] targeted frontend route suite passes
- [ ] semantic parity frontend suite passes
- [ ] semantic parity backend projector coverage passes
- [ ] staging or production-like smoke captured
- [ ] rollback validation recorded
