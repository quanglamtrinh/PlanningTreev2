# Phase 4 Verification Notes

Final verification completed on 2026-03-28:

- `npm run typecheck`
- `npx vitest run tests/unit/applyThreadEvent.test.ts tests/unit/threadStoreV2.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx tests/unit/Layout.test.tsx tests/unit/BreadcrumbChatView.test.tsx tests/unit/chat-store.test.ts`
- `npm run test:unit`

What this covered:

- V2 snapshot/upsert/patch reducer behavior
- `outputFilesReplace` overwriting preview data
- stale-load guards in the V2 store
- V2 thread stream URL wiring
- hidden `/chat-v2` shell parity
- local-review acceptance parity on `/chat-v2`
- Layout back-to-graph parity for hidden route
- V1 breadcrumb and V1 chat-store regression checks

Focused results:

- `npm run typecheck`: passed
- focused V2 + V1 regression suite: passed
- focused vitest summary: 6 files, 47 tests passed

Full frontend unit suite result:

- `npm run test:unit`: failed
- failure count: 1 failed file, 1 failed test, 19 passed files, 135 passed tests
- failing test:
  - `tests/unit/NodeDetailCard.test.tsx > NodeDetailCard > shows execution lifecycle badge separately from coarse node status`
  - assertion expects `Execution Complete`

Blocker triage:

- the failure reproduces in the legacy graph/detail `NodeDetailCard` path
- rendered DOM for the failure shows the legacy detail card and workflow stepper, not the hidden V2 conversation surface
- `frontend/src/features/node/NodeDetailCard.tsx` imports detail-state panels and workflow UI only; it does not import the V2 conversation stack
- `tests/unit/BreadcrumbChatViewV2.test.tsx`, `tests/unit/Layout.test.tsx`, and `tests/unit/threadStoreV2.test.ts` all passed in the same verification cycle
- classification: unrelated baseline failure outside Phase 4 hidden `/chat-v2` scope
- disposition: documented waiver for Phase 4 closeout; follow-up belongs to the legacy detail-panel test/component path

Smoke evidence summary:

- non-review breadcrumb shell with detail pane: covered by `BreadcrumbChatViewV2.test.tsx`
- ask/audit prefix parity on non-review nodes: covered by `BreadcrumbChatViewV2.test.tsx`
- review-node audit-only layout: covered by `BreadcrumbChatViewV2.test.tsx`
- local-review acceptance tab reset + sibling `/chat-v2` navigation: covered by `BreadcrumbChatViewV2.test.tsx`
- stale-target guard behavior: covered by `threadStoreV2.test.ts`
- hidden route parity in shell chrome: covered by `Layout.test.tsx`
- access notes for Electron/manual review: see `smoke-checklist.md`
