# Phase 3: Frontend Route, Screen, and Polling

Status: not started.

Effort: 20% (about 4.5 engineering days).

Depends on: Phase 1.

## Goal

Ship a dedicated Usage Snapshot page powered by backend local usage API with stable polling and robust UI states.

## Scope

- Add route `/usage-snapshot`.
- Add page component and styles.
- Add API typing and client call.
- Add polling hook with stale-response guard.
- Support manual refresh.

## Detailed implementation checklist

## 1) Extend API types

Update `frontend/src/api/types.ts` with:

- `LocalUsageDay`
- `LocalUsageTotals`
- `LocalUsageModel`
- `LocalUsageSnapshot`

Naming convention:

- follow backend snake_case fields in API layer for consistency.
- map to display-friendly values in component layer only.

## 2) Add API client method

Update `frontend/src/api/client.ts`:

- add method:
  - `getLocalUsageSnapshot(days?: number): Promise<LocalUsageSnapshot>`
- endpoint:
  - `/v1/codex/usage/local`
- include query param only when needed.
- reuse existing auth/header helper flow.

## 3) Add polling hook

Create `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts`:

- state:
  - `snapshot`
  - `isLoading`
  - `error`
- actions:
  - `refresh()`
- behavior:
  - initial fetch on mount
  - periodic fetch interval (baseline: 5 minutes)
  - manual refresh support
  - request generation id guard to prevent stale-overwrite

## 4) Build Usage Snapshot page

Create `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx` and CSS module.

Layout requirements:

- keep app shell visual language consistent with graph view.
- include:
  - page title and short subtitle
  - updated timestamp
  - manual refresh button
  - summary cards
  - 7-day chart
  - top-model section
  - error and empty states

Data rules:

- screen always requests all sessions (no workspace selector).
- support zero-data empty state cleanly.

## 5) Register route

Update `frontend/src/App.tsx`:

- add route:
  - `path="/usage-snapshot"`
  - `element={<UsageSnapshotPage .../>}`

Update any shell state handling if route-specific behavior is needed.

## 6) Add frontend unit tests

Add `frontend/tests/unit/UsageSnapshotPage.test.tsx`:

- loading skeleton render
- empty state render
- populated render
- manual refresh invokes hook action
- error state render and recover behavior

Add hook-focused tests if needed:

- polling interval behavior
- stale response ignored when newer request resolves first

## File targets

- `frontend/src/App.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx` (new)
- `frontend/src/features/usage-snapshot/UsageSnapshotPage.module.css` (new)
- `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts` (new)
- `frontend/tests/unit/UsageSnapshotPage.test.tsx` (new)

## Verification commands

- `npm run typecheck --prefix frontend`
- `npm run test:unit --prefix frontend -- tests/unit/UsageSnapshotPage.test.tsx`

## Deliverables

- `/usage-snapshot` route is live and data-driven.
- Polling behavior is deterministic and stale-safe.
- Feature-level frontend unit tests are green.

## Exit criteria

- Page loads and refreshes correctly against backend API.
- No blocker-level UI regression remains open.
- Phase 4 can integrate sidebar entrypoint cleanly.
