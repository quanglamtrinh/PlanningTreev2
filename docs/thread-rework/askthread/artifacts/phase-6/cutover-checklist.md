# Ask V3 Phase 6 Cutover Checklist

Date: 2026-04-03

## Gate and bootstrap contract

- [x] Backend env gates added:
  - `PLANNINGTREE_ASK_V3_BACKEND_ENABLED` (default `true`)
  - `PLANNINGTREE_ASK_V3_FRONTEND_ENABLED` (default `true`)
- [x] `/v1/bootstrap/status` exposes:
  - `ask_v3_backend_enabled`
  - `ask_v3_frontend_enabled`

## Ask stream and guard metrics

- [x] Ask rollout counters implemented:
  - `ask_stream_session_total`
  - `ask_stream_reconnect_total`
  - `ask_stream_error_total`
  - `ask_guard_violation_total`
  - `ask_shaping_action_total`
  - `ask_shaping_action_failed_total`
- [x] Frontend can report ask stream reconnect/error events.
- [x] Backend exposes read-only metrics endpoint:
  - `GET /v1/ask-rollout/metrics`
- [x] Backend accepts frontend metric events:
  - `POST /v1/ask-rollout/metrics/events`

## Runtime and route state

- [x] Ask V3 by-id route enforces typed gate error (`ask_v3_disabled`) when backend gate is off.
- [x] Legacy `/chat` surface redirects to `/chat-v2?thread=ask`.
- [x] Ask lane navigation is canonical on `/chat-v2`.

## Exit criteria probe (implementation-level)

- [x] Ask guard violation metric increments on policy violation path.
- [x] Ask shaping action metrics increment on generation/confirm endpoints.
- [x] Stream session metric increments for ask by-id SSE.
