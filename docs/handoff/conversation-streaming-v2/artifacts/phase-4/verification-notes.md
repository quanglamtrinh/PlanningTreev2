# Phase 4 Verification Notes

Focused verification completed on 2026-03-28:

- `npm run typecheck`
- `npx vitest run tests/unit/applyThreadEvent.test.ts tests/unit/threadStoreV2.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx tests/unit/Layout.test.tsx tests/unit/BreadcrumbChatView.test.tsx tests/unit/chat-store.test.ts`

What this covered:

- V2 snapshot/upsert/patch reducer behavior
- `outputFilesReplace` overwriting preview data
- stale-load guards in the V2 store
- V2 thread stream URL wiring
- hidden `/chat-v2` shell parity
- local-review acceptance parity on `/chat-v2`
- Layout back-to-graph parity for hidden route
- V1 breadcrumb and V1 chat-store regression checks

Known baseline noise outside Phase 4 scope:

- full frontend unit suite still includes an unrelated failure in `tests/unit/NodeDetailCard.test.tsx`
