# Ask Thread V3 Phase 6-7 Handoff

Date: 2026-04-03

## Scope locked for this handoff

- Phase 6: rollout gate contract + telemetry/stabilization hooks.
- Phase 7: hard cutover cleanup for ask lane.
- Ask remains a dedicated V3 lane with metadata shell UX and registry-first thread identity.

## Phase 6 completion (Gate rollout + stabilization)

Status: PASS

- Added backend gate config:
  - `PLANNINGTREE_ASK_V3_BACKEND_ENABLED` (default `true`)
  - `PLANNINGTREE_ASK_V3_FRONTEND_ENABLED` (default `true`)
- Exposed gate flags via `/v1/bootstrap/status`:
  - `ask_v3_backend_enabled`
  - `ask_v3_frontend_enabled`
- Added typed backend error for ask V3 gate-off:
  - `ask_v3_disabled` (`409`)
- Added ask rollout metrics service + API:
  - `GET /v1/ask-rollout/metrics`
  - `POST /v1/ask-rollout/metrics/events`
- Wired metrics into runtime:
  - ask stream session count (`/v3 by-id .../events`)
  - ask guard violation count (policy fail path)
  - ask shaping action totals/failures (`frame/clarify/spec` generate/confirm endpoints)
- Wired frontend V3 store telemetry for ask lane:
  - stream reconnect event
  - stream error event

## Phase 7 completion (Hard cutover cleanup)

Status: PASS

- Legacy `/chat` surface is now a thin redirect to `/chat-v2?thread=ask`.
- Ask V2 thread role path is removed from runtime behavior:
  - `/v2 .../threads/ask_planning*` returns typed invalid request.
- Legacy V1 ask handlers are disabled:
  - `/v1 .../chat/*` with default ask role now returns invalid request with migration message.
- Frontend legacy ask stack cleanup:
  - removed `chat-store`
  - removed V1 ask API client methods
  - removed ask fallback bootstrap through V2 snapshot
- Ask lane remains canonical on V3 by-id flow.

## Test evidence

### Frontend

```bash
npm run typecheck
npm run test:unit --prefix frontend
```

Result:

- Typecheck PASS
- Unit tests PASS (`33 passed`, `174 tests`)

### Backend (Phase 6-7 targeted)

```bash
python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_project_service.py backend/tests/unit/test_thread_readonly.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py
```

Result:

- PASS (`33 passed`)

## Artifacts

- `docs/thread-rework/askthread/artifacts/phase-6/cutover-checklist.md`
- `docs/thread-rework/askthread/artifacts/phase-6/smoke-results.md`
- `docs/thread-rework/askthread/artifacts/phase-6/rollback-notes.md`

## Known notes

- Full workspace `backend/tests/unit` currently reports unrelated pre-existing failures outside Phase 6-7 scope; targeted Phase 6-7 tests pass.
