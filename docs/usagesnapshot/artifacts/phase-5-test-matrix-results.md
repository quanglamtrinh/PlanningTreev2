# Phase 5 Test Matrix Results

Date: 2026-04-07

Status: PASS

## Commands executed

1. `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
2. `python -m pytest backend/tests/integration/test_codex_api.py -q`
3. `npm run test:unit --prefix frontend`
4. `npm run typecheck --prefix frontend`
5. `npm run test:e2e --prefix frontend -- usage-snapshot.spec.ts`
6. `npm run test:e2e --prefix frontend -- core-graph.spec.ts usage-snapshot.spec.ts`
7. `npm run test:e2e --prefix frontend`

## Results

- Backend unit: `15 passed`
- Backend integration: `11 passed`
- Frontend unit: `36 files`, `212 tests` passed
- Frontend typecheck: passed
- Usage Snapshot e2e (targeted): `2 passed`
- Combined e2e (core + usage): `3 passed`
- Full e2e suite: `3 passed`

## Flaky points observed during phase execution

1. Playwright strict-mode locator ambiguity from duplicated text matches.
2. Usage snapshot refresh-failure scenario was sensitive to request ordering during mount.
3. Early setup race when waiting on sidebar/project list text during app bootstrap.

## Mitigation actions applied

1. Switched to stable role/testid selectors (for example heading and explicit test ids) instead of broad text-only selectors.
2. Made usage-failure E2E deterministic by toggling failure only after initial content render, not by fixed call count.
3. Removed fragile sidebar project-name dependency in setup; seeded project via API and loaded active project through localStorage/reload (`domcontentloaded`) for core baseline.
4. Set E2E timeouts to `90_000` for these specs and ran usage snapshot tests in serial mode for stability.

## Final gate statement

Phase 5 acceptance matrix is green with deterministic E2E coverage and no unresolved blocker for Phase 6 kickoff.
