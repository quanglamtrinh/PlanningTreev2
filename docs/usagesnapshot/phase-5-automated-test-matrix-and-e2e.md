# Phase 5: Automated Test Matrix and E2E

Status: not started.

Effort: 19% (about 4.5 engineering days).

Depends on: Phase 2, Phase 3, Phase 4.

## Goal

Lock correctness and regression safety through a complete automated test matrix across backend and frontend layers.

## Scope

- Backend unit and integration coverage expansion.
- Frontend unit coverage for route and UI behavior.
- New Playwright E2E for sidebar-to-screen journey and snapshot rendering.

## Test matrix (authoritative)

Backend unit:

- parser handles total usage only
- parser handles mixed last + total usage without double count
- parser ignores malformed JSON lines
- parser ignores oversized lines
- run/time counting behavior
- model attribution fallback behavior
- cache hit/miss behavior

Backend integration:

- `/v1/codex/usage/local` returns valid shape
- days clamping behavior (`0`, negative, non-number, over max)
- route remains stable with empty sessions directory

Frontend unit:

- usage page loading, empty, error, data states
- manual refresh action behavior
- polling stale response guard
- sidebar button route navigation

Frontend E2E (Playwright):

- open app root route
- click sidebar `Usage Snapshot` button
- assert URL includes `/usage-snapshot`
- assert core blocks visible:
  - page heading
  - summary cards
  - chart area
- optional:
  - manual refresh button remains enabled after load

## Detailed implementation checklist

## 1) Backend unit tests

Create/extend:

- `backend/tests/unit/test_local_usage_snapshot_service.py`

Add fixtures and helpers for deterministic jsonl payload simulation.

## 2) Backend integration tests

Extend:

- `backend/tests/integration/test_codex_api.py`

Use test app state overrides where needed to isolate route behavior.

## 3) Frontend unit tests

Create/extend:

- `frontend/tests/unit/UsageSnapshotPage.test.tsx`
- `frontend/tests/unit/Sidebar.test.tsx`

Mock API client as needed to control state transitions.

## 4) Frontend E2E test

Create:

- `frontend/tests/e2e/usage-snapshot.spec.ts`

Guidance:

- seed at least one attached project so sidebar is visible in expected state.
- mock or prepare backend usage route response deterministically for reliability.

## 5) CI verification notes

Record in artifact docs:

- exact test commands
- pass/fail status
- flaky behavior observed
- mitigation actions

## File targets

- `backend/tests/unit/test_local_usage_snapshot_service.py`
- `backend/tests/integration/test_codex_api.py`
- `frontend/tests/unit/UsageSnapshotPage.test.tsx`
- `frontend/tests/unit/Sidebar.test.tsx`
- `frontend/tests/e2e/usage-snapshot.spec.ts`
- `docs/usagesnapshot/artifacts/phase-5-*.md` (new notes)

## Verification commands

- `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
- `python -m pytest backend/tests/integration/test_codex_api.py -q`
- `npm run test:unit --prefix frontend`
- `npm run test:e2e --prefix frontend -- usage-snapshot.spec.ts`

## Deliverables

- Feature path is covered by backend + frontend + E2E tests.
- Known flaky points are documented with mitigation.

## Exit criteria

- Required matrix is green in local run and CI.
- No unresolved blocker in feature tests.
