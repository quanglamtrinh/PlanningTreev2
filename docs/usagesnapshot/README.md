# Usage Snapshot Rollout Plan

Status: Phase 4 completed. Phase 5 is ready to start.

Last updated: 2026-04-06.

## Primary docs

- `docs/usagesnapshot/usagesnapshot-phased-roadmap.md`
- `docs/usagesnapshot/progress.yaml`
- `docs/usagesnapshot/phase-0-contract-freeze.md`
- `docs/usagesnapshot/phase-0-to-phase-1-handoff.md`
- `docs/usagesnapshot/phase-1-backend-scanner-and-api-foundation.md`
- `docs/usagesnapshot/phase-1-to-phase-2-handoff.md`
- `docs/usagesnapshot/phase-2-backend-performance-and-observability.md`
- `docs/usagesnapshot/phase-2-to-phase-3-handoff.md`
- `docs/usagesnapshot/phase-3-to-phase-4-handoff.md`
- `docs/usagesnapshot/phase-3-frontend-route-screen-and-polling.md`
- `docs/usagesnapshot/phase-4-sidebar-entrypoint-and-ux-polish.md`
- `docs/usagesnapshot/phase-4-to-phase-5-handoff.md`
- `docs/usagesnapshot/phase-5-automated-test-matrix-and-e2e.md`
- `docs/usagesnapshot/phase-6-rollout-and-stabilization.md`
- `docs/usagesnapshot/phase-7-cleanup-and-closeout.md`
- `docs/usagesnapshot/artifacts/README.md`

## Phase 0 completion outputs

- `docs/usagesnapshot/artifacts/phase-0-current-state-evidence.md`
- `docs/usagesnapshot/artifacts/phase-0-contract-checklist.md`
- `docs/usagesnapshot/artifacts/phase-0-ui-state-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-test-acceptance-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-deferred-backlog.md`

## Phase 1 completion outputs

- `docs/usagesnapshot/phase-1-backend-scanner-and-api-foundation.md`
- `docs/usagesnapshot/phase-1-to-phase-2-handoff.md`

## Phase 2 completion outputs

- `docs/usagesnapshot/phase-2-backend-performance-and-observability.md`
- `docs/usagesnapshot/phase-2-to-phase-3-handoff.md`

## Phase 3 completion outputs

- `docs/usagesnapshot/phase-3-frontend-route-screen-and-polling.md`
- `docs/usagesnapshot/phase-3-to-phase-4-handoff.md`

## Phase 4 completion outputs

- `docs/usagesnapshot/phase-4-sidebar-entrypoint-and-ux-polish.md`
- `docs/usagesnapshot/phase-4-to-phase-5-handoff.md`

## Locked decisions

- A dedicated Usage Snapshot screen is required.
- Entry point is the Usage Snapshot button in the sidebar usage area (current placement is under usage block).
- Data scope is all Codex sessions from Codex home (no project/workspace filter).
- Frontend data flow uses polling, not an SSE subscription for this feature.
- Delivery includes backend API, frontend UI, polling behavior, and automated tests including E2E.

## Current baseline

- Existing sidebar usage shows account rate limits and credits from:
  - backend route: `/v1/codex/account`
  - SSE route: `/v1/codex/events`
  - frontend store: `useCodexStore`
- Local usage snapshot API exists in PlanningTreeMain backend:
  - backend route: `/v1/codex/usage/local`
  - service: `LocalUsageSnapshotService`
  - parser supports `total_token_usage` + `last_token_usage`
  - route fallback semantics for `days`: default `30`, clamp `[1, 90]`, invalid -> `30`
- Usage Snapshot route and page now exist in PlanningTreeMain frontend:
  - route: `/usage-snapshot`
  - page: `UsageSnapshotPage`
  - hook: `useLocalUsageSnapshot` (polling + manual refresh + stale guard)
- CodexMonitor already has a reference implementation of local usage aggregation over `.codex/sessions`.

## Migration shape

Phase order:

1. Phase 0: contract freeze and implementation boundaries
2. Phase 1: backend scanner and API foundation
3. Phase 2: backend performance, cache, resilience, observability
4. Phase 3: frontend route, page, polling hook, API integration
5. Phase 4: sidebar UX polish and accessibility follow-through
6. Phase 5: automated test matrix and E2E coverage
7. Phase 6: rollout and stabilization
8. Phase 7: cleanup and closeout

Critical dependency chain:

- Phase 0 must complete before implementation.
- Phase 1 must complete before frontend integration in Phase 3.
- Phase 2 should complete before Phase 5 performance validation.
- Phase 3 must complete before full sidebar UX closeout in Phase 4.
- Phase 5 must pass before rollout in Phase 6.
- Phase 7 starts only after stabilization sign-off from Phase 6.

## Cross-phase rules

- Keep feature isolated from existing codex account snapshot flow until explicitly merged.
- Do not expand scope to workspace-specific filtering in this track.
- Preserve API compatibility for existing `/v1/codex/account` and `/v1/codex/events`.
- Keep scan logic deterministic and idempotent for the same input files.
- Avoid silent parsing failures that hide systemic regressions; add explicit counters/logging.
- Keep test artifacts reproducible and checked into docs under `docs/usagesnapshot/artifacts`.

## Required outputs per phase

Each phase must update:

- its phase markdown file in `docs/usagesnapshot/`
- `docs/usagesnapshot/progress.yaml`
- test evidence and notes in `docs/usagesnapshot/artifacts/`

## Recommended PR shape

- Prefer one primary PR per phase.
- If phase is split across multiple PRs, each PR should still preserve phase exit criteria.
- Do not mark a phase completed until verification notes and artifacts are recorded.

## Definition of done for this track

- `/usage-snapshot` page is reachable from sidebar button.
- Page displays local usage snapshot aggregated from all Codex sessions.
- Data refreshes by polling and supports manual refresh.
- Backend and frontend test matrix (unit + integration + E2E) is green for this feature path.
- Rollout checklist and closeout docs are complete.
