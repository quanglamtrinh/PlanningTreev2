# Usage Snapshot Phase 5 to Phase 6 Handoff

Status: ready for Phase 6 implementation.

Date: 2026-04-08.

Owner scope: transition from automated matrix hardening to rollout and stabilization execution.

## 1. Purpose

Phase 5 is complete and re-validated after flaky baseline E2E stabilization. This handoff locks test and behavior contracts so Phase 6 can focus on rollout checklist execution and runtime stabilization without reopening feature scope.

## 2. Phase 5 outcome at a glance

Phase 5 target was: close automated test matrix for Usage Snapshot and remove E2E baseline blocker tied to legacy create-child flow.

Outcome: delivered and stabilized.

## 3. Implementation inventory (what shipped)

### 3.1 Baseline E2E migrated to `Create A Task`

Updated `frontend/tests/e2e/core-graph.spec.ts`:

1. baseline path now uses `Node actions -> Create A Task`.
2. fills `#create-task-description` and confirms with `Confirm Task`.
3. asserts task can be opened in breadcrumb via `Open in Breadcrumb`.
4. no dependency on `Create Child`.

### 3.2 Baseline E2E flaky hardening (post-review stabilization)

Same file `frontend/tests/e2e/core-graph.spec.ts` was hardened to remove race conditions found during Phase 5 review:

1. waits for `GET /v1/projects/{projectId}/snapshot` after setting active project id and reload.
2. waits for any graph node presence (`[data-testid^="graph-node-"]`) rather than a strict root-node-id render race.
3. tolerates async surface transition after task creation:
   - if breadcrumb is open, clicks `Back to Graph`
   - waits until new task node becomes visible
4. keeps deterministic reopen assertion through `Open in Breadcrumb` on the task node.

### 3.3 Usage Snapshot E2E delivered

Created `frontend/tests/e2e/usage-snapshot.spec.ts`:

1. deterministic route mocking for `GET /v1/codex/usage/local*`.
2. verifies sidebar navigation to `/usage-snapshot`.
3. verifies heading, summary region, chart, and refresh control.
4. verifies non-blocking error banner on refresh failure while stale content remains visible.

### 3.4 Backend integration gap closed

Updated `backend/tests/integration/test_codex_api.py`:

1. added explicit empty-sessions-root stability test.
2. verifies `GET /v1/codex/usage/local?days=1` returns valid shape and zero usage when sessions are absent.

## 4. Locked behavior contract for Phase 6

Phase 6 should treat these as stable unless blocker-level issue appears:

1. Usage Snapshot route remains `/usage-snapshot`.
2. sidebar entrypoint remains under usage block with label/action semantics from Phase 4.
3. data scope remains all codex sessions (no workspace filtering).
4. polling + manual refresh contract remains unchanged.
5. baseline E2E contract for graph flow is `Create A Task` (not `Create Child`).
6. no public API/schema change is required for rollout.

## 5. Verification evidence

Re-validated during review hardening on 2026-04-08:

1. `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
   - result: `15 passed`
2. `python -m pytest backend/tests/integration/test_codex_api.py -q`
   - result: `11 passed`
3. `npm run test:unit --prefix frontend`
   - result: `36 files`, `212 tests` passed
4. `npm run typecheck --prefix frontend`
   - result: pass
5. `npm run test:e2e --prefix frontend -- core-graph.spec.ts usage-snapshot.spec.ts` (run multiple times)
   - result: pass (`3 passed`)
6. `npm run test:e2e --prefix frontend`
   - result: pass (`3 passed`)

## 6. Known non-blocking notes

1. existing React Router future-flag warnings still appear in unit tests and are unrelated to Usage Snapshot delivery.
2. Playwright runs generate temporary directories under `frontend/tests/e2e/.tmp`; keep cleanup in normal test hygiene if needed.

## 7. Phase 6 kickoff checklist

Recommended start checklist for the next owner:

1. use Phase 5 docs + this handoff as rollout contract source of truth.
2. execute Phase 6 rollout checklist in production-like runtime.
3. record rollout/stabilization artifacts:
   - `docs/usagesnapshot/artifacts/phase-6-rollout-checklist.md`
   - `docs/usagesnapshot/artifacts/phase-6-stabilization-notes.md`
4. do not expand scope to filtering/refactor work during stabilization.
5. only ship bug-fix changes that are blocker/high for rollout safety.

## 8. Open blockers/questions

No blocker remains for Phase 6 kickoff.

## 9. Artifact index

- `docs/usagesnapshot/phase-5-automated-test-matrix-and-e2e.md`
- `docs/usagesnapshot/artifacts/phase-5-test-matrix-results.md`
- `docs/usagesnapshot/phase-5-to-phase-6-handoff.md`
- `docs/usagesnapshot/phase-6-rollout-and-stabilization.md`
- `docs/usagesnapshot/progress.yaml`

Phase gate outcome: Phase 5 PASS (stabilized), Phase 6 READY.
