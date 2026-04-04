# Ask V3 Phase 6 Rollback Notes

Date: 2026-04-03

## Runtime rollback levers (Phase 6)

- Backend gate:
  - `PLANNINGTREE_ASK_V3_BACKEND_ENABLED=false`
  - Effect: ask by-id V3 APIs return typed error `ask_v3_disabled`.
- Frontend gate:
  - `PLANNINGTREE_ASK_V3_FRONTEND_ENABLED=false`
  - Contract exposed via `/v1/bootstrap/status` for client-side effective gating.

## Operational checks before rollback

- Validate stream health via `GET /v1/ask-rollout/metrics`.
- Confirm whether failures are reconnect-heavy (`ask_stream_reconnect_total`) or hard errors (`ask_stream_error_total`).
- Confirm no write-policy incident (`ask_guard_violation_total` remains `0`).

## Phase 7 policy update

- After hard cutover cleanup, rollback is release-based (deploy rollback), not runtime fallback ask routing.
