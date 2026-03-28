# Phase 4 Implementation Notes

Date: 2026-03-28

Landed slices:

- hidden `/chat-v2` route
- breadcrumb route parity in `Layout`
- V2 frontend type surface and V2 API client helpers
- V2 thread store, event applier, and thread/workflow event parsing
- generation-token stale guards for load/send/reset/reconnect/SSE paths
- direct render-by-kind conversation components
- hidden breadcrumb shell with prefix/detail-pane/review-layout parity
- ask-thread reset action in header
- local-review acceptance parity on `/chat-v2`

Intentional mixed-mode boundary that remains:

- `/chat` stays on V1
- detail-state loading stays on current detail APIs
- local-review acceptance stays on current detail APIs

Completion/sign-off notes:

- Phase 4 was closed after focused V2 + V1 regression verification passed and the remaining full-suite blocker was triaged.
- The remaining `NodeDetailCard` failure was classified as legacy detail-panel baseline noise, not a hidden `/chat-v2` regression.
- `/chat-v2` is now the intended rehearsal surface for Phase 5.
