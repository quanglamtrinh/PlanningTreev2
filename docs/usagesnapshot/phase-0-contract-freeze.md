# Phase 0: Contract Freeze and Boundaries

Status: completed.

Last updated: 2026-04-06.

Effort: 8% (about 2.0 engineering days).

## Goal

Freeze API contract, parser semantics, UI behavior, and scope boundaries before Phase 1 implementation.

## Phase completion summary

- Decision pack is finalized with no open technical ambiguity for Phase 1.
- Baseline compatibility with current PlanningTreeMain architecture is documented.
- API/parser/UI/test contracts are locked and traceable.
- Deferred scope is explicitly listed to prevent implementation creep.

## Inputs

- `docs/usagesnapshot/README.md`
- `docs/usagesnapshot/usagesnapshot-phased-roadmap.md`

## Execution slots outcome

| Slot | Owner role | Output | Status |
|---|---|---|---|
| A (0.5d) | Tech lead + BE lead | Current-state evidence and compatibility check | completed |
| B (0.75d) | BE lead | API/parser contract freeze | completed |
| C (0.5d) | FE lead | UX/route/state/refresh contract freeze | completed |
| D (0.25d) | QA lead | Test acceptance matrix freeze | completed |
| E (buffer) | Leads | Conflict cleanup + tracker update | completed |

## Locked product decisions for this phase

- Dedicated Usage Snapshot screen is required.
- Sidebar button entrypoint is required.
- Scope is all Codex sessions only.
- Refresh strategy is polling plus manual refresh.
- Delivery includes backend + frontend + tests including E2E.

## In scope

- Define API route, query params, and response shape.
- Define parser semantic rules and aggregation formulas.
- Define UI states and fallback behavior.
- Define test acceptance matrix for all later phases.

## Out of scope

- Coding scanner, route, or UI.
- Adding workspace-level filter options.
- Reworking existing codex account/rate-limit snapshot behavior.
- Replacing `/v1/codex/events` SSE with a new usage-specific SSE flow.
- Persistence layer for historical aggregate snapshots.

## Current-state compatibility evidence

Reference: `docs/usagesnapshot/artifacts/phase-0-current-state-evidence.md`

Compatibility conclusion:

- Existing codex account/rate-limit flows remain isolated and can coexist with new usage-local route.
- App routing/shell structure allows adding `/usage-snapshot` without breaking existing graph/chat surfaces.
- Existing test stack already supports required unit + E2E layers.

## Contract freeze (decision complete)

## API contract

Route:

- `GET /v1/codex/usage/local`

Query params:

- `days` optional integer
- default `30`
- clamp `[1, 90]`
- invalid parse falls back to default `30` (no hard validation error)

Response contract:

- snake_case fields only
- fixed shape with:
  - `updated_at`
  - `days[]`
  - `totals`
  - `top_models[]`

Reference payload and field checklist:

- `docs/usagesnapshot/artifacts/phase-0-contract-checklist.md`

## Parser and aggregation contract

Root and traversal:

- session root = `$CODEX_HOME/sessions` else `~/.codex/sessions`
- day folder traversal by `YYYY/MM/DD`
- only `.jsonl` files
- unreadable files are skipped safely

Event handling:

- support both `total_token_usage` and `last_token_usage`
- per-file delta logic must prevent double counting
- `agent_runs` from assistant message events
- `agent_time_ms` from timestamp delta with `MAX_ACTIVITY_GAP_MS = 120000`
- day bucket uses local timezone on backend host

Totals semantics:

- `last7_days_tokens` = sum of most recent 7 days in selected scan window
- `last30_days_tokens` = sum of most recent max 30 days in selected scan window
- `average_daily_tokens` = rounded average over the same most recent 7-day set
- `cache_hit_rate_percent` = `cached_input_tokens / input_tokens * 100`, rounded to 1 decimal
- `peak_day` and `peak_day_tokens` from max `total_tokens` day within scan window

Model leaderboard:

- sort by descending `tokens`
- exclude `unknown`
- keep top 4
- `share_percent` rounded to 1 decimal

## Error policy

- malformed JSON line: skip line, continue scan
- oversized line: skip line, continue scan
- unreadable file: skip file, continue scan
- route should prefer valid empty snapshot fallback when scan is partially degraded
- 5xx is reserved for service-level unsafe initialization/fatal failure

## Frontend contract freeze

- route path: `/usage-snapshot`
- entrypoint button located above current sidebar usage block
- data refresh: initial load + interval polling + manual refresh
- stale-response guard required via request generation id
- no SSE for usage snapshot in this track

UI state matrix and interaction notes:

- `docs/usagesnapshot/artifacts/phase-0-ui-state-matrix.md`

## Test acceptance contract freeze

Frozen matrix:

- backend unit: parser and aggregation rules
- backend integration: route shape + days behavior
- frontend unit: usage page states + refresh behavior
- frontend unit: sidebar navigation to usage route
- frontend E2E: sidebar entrypoint to loaded usage screen

Reference:

- `docs/usagesnapshot/artifacts/phase-0-test-acceptance-matrix.md`

## Traceability and sign-off checklist

Contract traceability:

- `dedicated_usage_snapshot_screen` -> phase-0 sections `Frontend contract freeze` + UI matrix
- `sidebar_button_entrypoint` -> phase-0 sections `Frontend contract freeze` + UI matrix
- `all_codex_sessions_scope` -> phase-0 sections `Parser and aggregation contract`
- `polling_refresh_strategy` -> phase-0 sections `Frontend contract freeze`
- `full_delivery_scope` -> phase-0 sections `Test acceptance contract freeze`

Role sign-off checklist:

- [x] BE lead sign-off recorded (API/parser/error policy)
- [x] FE lead sign-off recorded (route/UX/states/refresh policy)
- [x] QA lead sign-off recorded (test acceptance matrix)

## Deferred scope guard

Deferred backlog (explicitly non-phase-0 and non-phase-1 decisions):

- workspace/project filter
- SSE-based usage push updates
- persisted aggregate database/cache
- deep drill-down analytics

Reference:

- `docs/usagesnapshot/artifacts/phase-0-deferred-backlog.md`

## Phase 0 deliverables

- `docs/usagesnapshot/artifacts/phase-0-current-state-evidence.md`
- `docs/usagesnapshot/artifacts/phase-0-contract-checklist.md`
- `docs/usagesnapshot/artifacts/phase-0-ui-state-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-test-acceptance-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-deferred-backlog.md`

## Exit criteria

- API shape, parser semantics, UI states, and test matrix are frozen.
- All high-impact ambiguities are resolved.
- Deferred scope is explicitly documented.

## Phase gate decision

- Phase 0 gate: passed.
- Phase 1 kickoff status: ready.
