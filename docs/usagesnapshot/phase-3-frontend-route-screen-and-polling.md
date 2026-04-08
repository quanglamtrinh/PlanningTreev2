# Phase 3: Frontend Route, Screen, and Polling

Status: completed on 2026-04-06.

Effort: 20% (about 4.5 engineering days).

Depends on: Phase 1 (and consumes Phase 2 hardened backend behavior).

## Goal

Ship a dedicated Usage Snapshot page powered by backend local usage API with stable polling and robust UI states.

## Scope

- Add API typing and frontend client call for local usage snapshot.
- Add polling hook with stale-response guard and manual refresh action.
- Connect Usage Snapshot page to real backend data and state-driven UI.
- Keep route and app shell behavior stable.
- Add frontend unit tests for page, hook, and route shell behavior.

## Delivered implementation

## 1) API types and client contract

Updated `frontend/src/api/types.ts`:

- `LocalUsageDay`
- `LocalUsageTotals`
- `LocalUsageModel`
- `LocalUsageSnapshot`

Updated `frontend/src/api/client.ts`:

- `getLocalUsageSnapshot(days?: number): Promise<LocalUsageSnapshot>`
- endpoint: `/v1/codex/usage/local`
- query behavior: include `days` only when provided.

## 2) Polling hook with stale-overwrite protection

Created `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts` with:

- state:
  - `snapshot`
  - `isLoading`
  - `isRefreshing`
  - `error`
  - `lastSuccessfulAt`
- actions:
  - `refresh()`
- behavior:
  - initial fetch on mount
  - polling every 5 minutes
  - manual refresh support
  - request generation guard to ignore stale responses
  - unmount-safe cleanup for interval and post-unmount state updates
- days input standardized to `30` for Phase 3 reads.

## 3) Usage Snapshot page connected to live data

Updated:

- `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx`
- `frontend/src/features/usage-snapshot/UsageSnapshotPage.module.css`

Delivered UI states:

- initial loading skeleton
- blocking error state with retry when no data exists
- non-blocking error banner when stale data exists
- empty state when usage totals are zero
- populated state with:
  - updated timestamp
  - manual refresh control
  - summary cards
  - 7-day chart (native SVG/CSS)
  - top-model list

Shell continuity:

- kept existing shell (`Sidebar` + main column)
- kept existing route `/usage-snapshot`
- kept current sidebar entrypoint placement unchanged in this phase.

## 4) Frontend unit test coverage

Created:

- `frontend/tests/unit/UsageSnapshotPage.test.tsx`
- `frontend/tests/unit/useLocalUsageSnapshot.test.tsx`

Updated:

- `frontend/tests/unit/Layout.test.tsx` (Back to Graph on `/usage-snapshot`)

Validated test scenarios:

- page: loading, blocking error + retry, empty, populated, non-blocking error, manual refresh action
- hook: initial fetch, polling, stale response ignored, manual refresh state, interval cleanup
- layout: `/usage-snapshot` route shows Back to Graph and navigates to graph

## Verification commands

Executed:

- `npm run typecheck --prefix frontend`
- `npm run test:unit --prefix frontend -- tests/unit/useLocalUsageSnapshot.test.tsx tests/unit/UsageSnapshotPage.test.tsx tests/unit/Layout.test.tsx tests/unit/Sidebar.test.tsx`
- `npm run test:unit --prefix frontend`

Result:

- frontend typecheck passed
- frontend unit suite passed (`36 files`, `210 tests`)

## File targets delivered

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts` (new)
- `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx`
- `frontend/src/features/usage-snapshot/UsageSnapshotPage.module.css`
- `frontend/tests/unit/UsageSnapshotPage.test.tsx` (new)
- `frontend/tests/unit/useLocalUsageSnapshot.test.tsx` (new)
- `frontend/tests/unit/Layout.test.tsx`

## Deliverables

- `/usage-snapshot` route is data-driven.
- Polling behavior is deterministic and stale-safe.
- Manual refresh is stable (no forced cache bypass).
- Phase 4 integration work can proceed.

## Exit criteria

- Page loads and refreshes correctly against backend API.
- No blocker-level UI regression remains open.
- Phase 4 can focus on sidebar UX polish and accessibility follow-through.
