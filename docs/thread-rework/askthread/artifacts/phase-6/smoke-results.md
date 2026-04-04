# Ask V3 Phase 6 Smoke Results

Date: 2026-04-03

## Commands

```bash
npm run typecheck
npm run test:unit --prefix frontend
python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_project_service.py backend/tests/unit/test_thread_readonly.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py
```

## Result summary

- `npm run typecheck`: PASS
- `npm run test:unit --prefix frontend`: PASS (`33 passed`, `174 tests`)
- Targeted backend unit suite: PASS (`33 passed`)

## Metrics endpoint smoke (covered by test)

- `GET /v1/ask-rollout/metrics` returns initialized counters and computed rates.
- `POST /v1/ask-rollout/metrics/events` accepts:
  - `stream_reconnect`
  - `stream_error`
- Counters update is observable via follow-up `GET /v1/ask-rollout/metrics`.

## Notes

- A full `backend/tests/unit` run in this workspace currently reports unrelated pre-existing failures outside Phase 6-7 scope (clarify/spec/split/system-message-writer coupling). Phase 6-7 targeted tests passed.
