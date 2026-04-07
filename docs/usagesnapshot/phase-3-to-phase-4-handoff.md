# Usage Snapshot Phase 3 to Phase 4 Handoff

Status: ready for Phase 4 implementation.

Date: 2026-04-06.

Owner scope: transition from frontend data delivery to sidebar UX polish and accessibility finalization.

## 1. Purpose

Phase 3 is complete and validated. This handoff locks the frontend data/polling contract so Phase 4 can focus on UX polish without reopening API or data-lifecycle logic.

## 2. Phase 3 outcome at a glance

Phase 3 target was: real data on `/usage-snapshot`, stable polling/manual refresh, and baseline unit coverage for route/screen/hook behavior.

Outcome: delivered and verified.

## 3. Implementation inventory (what shipped)

### 3.1 Frontend API contract wiring

1. Typed models added in `frontend/src/api/types.ts`:
   - `LocalUsageDay`
   - `LocalUsageTotals`
   - `LocalUsageModel`
   - `LocalUsageSnapshot`
2. API client method added in `frontend/src/api/client.ts`:
   - `getLocalUsageSnapshot(days?: number)`
   - calls `GET /v1/codex/usage/local`
   - query param `days` is only sent when explicitly provided

### 3.2 Data lifecycle + polling

1. New hook `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts`.
2. Hook state:
   - `snapshot`
   - `isLoading`
   - `isRefreshing`
   - `error`
   - `lastSuccessfulAt`
3. Runtime behavior:
   - initial fetch on mount
   - polling interval: every 5 minutes
   - manual refresh trigger
   - standardized request window: `days=30`
4. Safety/consistency guards:
   - request generation guard prevents stale response overwrite
   - interval cleanup + unmount safety (no post-unmount state update)

### 3.3 Usage Snapshot page integration

1. Updated `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx`.
2. Updated `frontend/src/features/usage-snapshot/UsageSnapshotPage.module.css`.
3. Kept current shell behavior and existing sidebar/button placement.
4. Implemented full page state matrix:
   - initial loading skeleton
   - blocking error (no cached data) + retry action
   - non-blocking error banner (when stale data is present)
   - empty state when total usage is zero
   - populated state with:
     - title/subtitle + updated timestamp
     - manual refresh button with busy state
     - summary cards from totals
     - native 7-day chart (SVG/CSS, no new chart dependency)
     - top-model usage list

### 3.4 Route/layout continuity

1. Existing route `/usage-snapshot` remains unchanged at app shell level.
2. Existing topbar back-navigation behavior preserved.

## 4. Locked behavior contract for Phase 4

Phase 4 should treat these as stable unless blocker-level issue appears:

1. Data source remains `GET /v1/codex/usage/local` (no backend schema/endpoint change).
2. Scope remains all Codex sessions (no workspace filter in this phase path).
3. Polling cadence remains 5 minutes.
4. Manual refresh does not force backend cache bypass.
5. Usage snapshot entrypoint remains at current sidebar placement under the usage block.

## 5. Verification evidence

Executed during Phase 3 closeout:

1. `npm run typecheck --prefix frontend`
   - result: pass
2. `npm run test:unit --prefix frontend -- tests/unit/useLocalUsageSnapshot.test.tsx tests/unit/UsageSnapshotPage.test.tsx tests/unit/Layout.test.tsx tests/unit/Sidebar.test.tsx`
   - result: pass
3. `npm run test:unit --prefix frontend`
   - result: pass (`36 files`, `210 tests`)

## 6. Test coverage map (Phase 3)

1. `frontend/tests/unit/UsageSnapshotPage.test.tsx`
   - loading
   - populated render
   - empty state
   - blocking error + retry
   - non-blocking error with existing data
   - manual refresh interaction
2. `frontend/tests/unit/useLocalUsageSnapshot.test.tsx`
   - polling tick behavior
   - interval cleanup on unmount
   - stale response guard
   - manual refresh lifecycle
3. `frontend/tests/unit/Layout.test.tsx`
   - `/usage-snapshot` route shows back-to-graph control
4. `frontend/tests/unit/Sidebar.test.tsx`
   - usage snapshot navigation from sidebar

## 7. Known non-blocking notes

1. Manual refresh can still return cached snapshot within backend TTL (30 seconds) by design.
2. Existing unrelated test-suite warnings (react-router future flags / isolated act warnings in non-phase-3 tests) were observed previously and do not block Phase 4 kickoff.

## 8. Phase 4 kickoff checklist

Recommended start checklist for the next owner:

1. Review `docs/usagesnapshot/phase-4-sidebar-entrypoint-and-ux-polish.md` and confirm scope boundary (UX/a11y only).
2. Preserve `useLocalUsageSnapshot` contract and avoid altering fetch semantics unless a blocker is proven.
3. Validate:
   - route active visuals
   - keyboard navigation
   - focus visibility and tab order
   - responsive behavior for sidebar entrypoint
4. Keep `/usage-snapshot` page data rendering logic intact while polishing entrypoint UX.
5. Record any polish-driven test additions directly in phase-4 doc and progress log.

## 9. Forward seed for Phase 5 (E2E)

Phase 3 leaves clear seeds for E2E completion in Phase 5:

1. sidebar entrypoint click to `/usage-snapshot`
2. screen state transitions (loading -> populated / empty / error)
3. manual refresh interaction
4. periodic polling behavior (clock-controlled E2E where feasible)

## 10. Open blockers/questions

No blockers remain for Phase 4 implementation.

## 11. Artifact index

- `docs/usagesnapshot/phase-3-frontend-route-screen-and-polling.md`
- `docs/usagesnapshot/phase-3-to-phase-4-handoff.md`
- `docs/usagesnapshot/phase-4-sidebar-entrypoint-and-ux-polish.md`
- `docs/usagesnapshot/progress.yaml`

Phase gate outcome: Phase 3 PASS, Phase 4 READY.
