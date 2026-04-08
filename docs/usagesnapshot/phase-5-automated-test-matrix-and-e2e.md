# Phase 5: Automated Test Matrix and E2E

Status: completed on 2026-04-07.

Effort: 19% (about 4.5 engineering days).

Depends on: Phase 2, Phase 3, Phase 4.

## Goal

Lock correctness and regression safety through a complete automated test matrix across backend and frontend layers.

## Scope delivered

- Backend unit and integration matrix verification for local usage snapshot.
- Frontend unit verification for usage page state behavior and sidebar route behavior.
- Playwright E2E coverage for:
  - baseline graph journey (aligned to `Create A Task`, no `Create Child`)
  - sidebar-to-usage-snapshot journey with deterministic usage payload rendering
  - non-blocking error behavior after manual refresh failure with cached content

## Delivered implementation

## 1) Baseline E2E migration to `Create A Task`

Updated:

- `frontend/tests/e2e/core-graph.spec.ts`

Changes:

- replaced legacy `Node actions -> Create Child` flow with:
  - `Node actions -> Create A Task`
  - fill `#create-task-description`
  - `Confirm Task`
  - assert breadcrumb pane + task heading + back-to-graph control
  - return to graph, assert new task node, and re-open via `Open in Breadcrumb`
- hardened setup by setting active project id in `localStorage` and reloading with
  `domcontentloaded` wait.

## 2) New Usage Snapshot Playwright spec

Created:

- `frontend/tests/e2e/usage-snapshot.spec.ts`

Coverage:

- open root route, seed attached project, navigate via sidebar button `Open Usage Snapshot`
- assert URL includes `/usage-snapshot`
- assert key blocks:
  - page heading
  - summary section (`aria-label="Usage summary"`)
  - chart (`aria-label="7-day token chart"`)
- assert manual refresh button visible and enabled
- deterministic backend mocking via Playwright `page.route('**/v1/codex/usage/local*', ...)`
- verify non-blocking refresh failure behavior:
  - stale content remains visible
  - error banner appears after manual refresh failure

## 3) Backend integration matrix gap closure

Updated:

- `backend/tests/integration/test_codex_api.py`

Added:

- explicit test for empty sessions root stability:
  - `CODEX_HOME` set to empty path
  - `GET /v1/codex/usage/local?days=1`
  - assert valid shape + `days` length = `1` + `total_tokens = 0`

## 4) Phase evidence and docs updates

- added phase artifact report:
  - `docs/usagesnapshot/artifacts/phase-5-test-matrix-results.md`
- updated phase status and progress tracker:
  - `docs/usagesnapshot/progress.yaml`
- updated rollout overview status:
  - `docs/usagesnapshot/README.md`
  - `docs/usagesnapshot/artifacts/README.md`

## Test matrix status

Backend unit:

- parser total-only aggregation: covered
- mixed total+last semantics: covered
- malformed json / oversized line handling: covered
- run counting / time cap behavior: covered
- model attribution fallback: covered
- cache hit/miss + single-flight behavior: covered

Backend integration:

- `/v1/codex/usage/local` shape: covered
- days clamp/fallback behavior: covered
- degraded and empty sessions directory stability: covered

Frontend unit:

- usage page loading / empty / blocking / non-blocking states: covered
- manual refresh action behavior: covered
- stale response guard: covered
- sidebar route navigation semantics: covered

Frontend E2E:

- sidebar journey to `/usage-snapshot`: covered
- heading + summary + chart rendering: covered
- manual refresh control enabled state: covered
- non-blocking error banner after refresh failure: covered
- baseline graph journey aligned to current `Create A Task` UX: covered

## Verification commands and results

Executed:

- `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
  - result: pass (`15 passed`)
- `python -m pytest backend/tests/integration/test_codex_api.py -q`
  - result: pass (`11 passed`)
- `npm run test:unit --prefix frontend`
  - result: pass (`36 files`, `212 tests`)
- `npm run typecheck --prefix frontend`
  - result: pass
- `npm run test:e2e --prefix frontend -- usage-snapshot.spec.ts`
  - result: pass (`2 passed`)
- `npm run test:e2e --prefix frontend -- core-graph.spec.ts usage-snapshot.spec.ts`
  - result: pass (`3 passed`)
- `npm run test:e2e --prefix frontend`
  - result: pass (`3 passed`)

## Deliverables

- Phase 5 matrix is green across backend unit/integration, frontend unit/typecheck, and Playwright E2E.
- Baseline E2E now reflects current product behavior (`Create A Task`).
- Usage Snapshot E2E is deterministic and resilient against local `.codex/sessions` variance.
- Phase 6 can start without reopening Phase 5 blockers.

## Exit criteria

- Required matrix is green locally and CI-compatible.
- No unresolved blocker remains in feature tests for usage snapshot path.
