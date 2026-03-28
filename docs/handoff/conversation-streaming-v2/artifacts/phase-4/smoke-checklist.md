# Phase 4 Smoke Checklist

This artifact records the hidden-path review checklist used to close Phase 4.

In this automation turn, the checklist was satisfied primarily through executable route/store tests plus direct route-access notes. No separate screenshot or clip was captured.

## Hidden Route Access

Web dev route:

- `http://localhost:5174/projects/<projectId>/nodes/<nodeId>/chat-v2`

Electron dev route:

- open the current node on `/chat`
- use DevTools console
- run:

```js
window.history.pushState({}, '', window.location.pathname.replace(/\/chat$/, '/chat-v2'))
window.dispatchEvent(new PopStateEvent('popstate'))
```

## Checklist Outcome

- non-review `/chat-v2` shows breadcrumb shell with detail pane
  - covered by `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- ask/audit on non-review nodes keep `FrameContextFeedBlock`
  - covered by `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- review node forces audit and hides detail pane
  - covered by `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- local-review acceptance on audit resets tab to ask and navigates to sibling `/chat-v2`
  - covered by `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- ask-thread reset appears only when writable and converges through stream/reload semantics
  - covered by hidden-route implementation plus focused reducer/store verification
- stale route/tab changes do not leak old thread state into the current target
  - covered by `frontend/tests/unit/threadStoreV2.test.ts`
- breadcrumb-shell route parity for back-to-graph chrome
  - covered by `frontend/tests/unit/Layout.test.tsx`

## Notes

- Phase 4 evidence is primarily executable rather than screenshot-based.
- This is acceptable for Phase 4 closeout because the hidden route remains a rehearsal surface and the critical parity behaviors are already locked by dedicated unit/route tests.
