# Phase 0 Test Acceptance Matrix

Status: completed.

## Mandatory coverage by layer

| Layer | Test type | Required scenarios | Pass condition |
|---|---|---|---|
| Backend parser service | unit | total-only stream, mixed last+total, malformed line, oversized line, unreadable file, run/time accumulation | all expected aggregates match deterministic fixtures |
| Backend API | integration | route shape, days clamp behavior, empty snapshot fallback | route returns stable schema; no unhandled exception on degraded input |
| Frontend usage page | unit | loading/loaded/empty/error states, manual refresh action, stale-response guard behavior | state transitions match UI contract with no stale overwrite |
| Frontend sidebar | unit | usage entrypoint button renders and navigates to `/usage-snapshot` | route update and focus behavior are stable |
| Frontend full flow | E2E (Playwright) | open app, click sidebar entrypoint, route arrives at usage page, key blocks visible | user can reach and view Usage Snapshot end-to-end |

## Required command families

Backend:

- `python -m pytest backend/tests/unit/...`
- `python -m pytest backend/tests/integration/...`

Frontend:

- `npm run test:unit --prefix frontend`
- `npm run test:e2e --prefix frontend`

## Minimum regression guardrails

- Existing codex account snapshot flow (`/v1/codex/account`) remains unaffected.
- Existing codex SSE flow (`/v1/codex/events`) remains unaffected.
- Existing graph/chat routes continue to resolve as before.

## Phase gate condition

Phase 1 implementation starts only when this matrix is accepted as the minimum bar and mapped to concrete test files in later phases.
