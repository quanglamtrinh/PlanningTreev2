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

Follow-up items before Phase 4 can be marked complete:

- broader frontend verification pass once unrelated baseline test noise is resolved
- screenshot/evidence capture for shell parity and reset flow
