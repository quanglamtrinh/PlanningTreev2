# Phase 0: Contract Freeze and Boundaries

Status: not started.

Effort: 8% (about 2.0 engineering days).

## Goal

Freeze API contract, parser semantics, UI behavior, and scope boundaries before coding.

## Inputs

- `docs/usagesnapshot/README.md`
- `docs/usagesnapshot/usagesnapshot-phased-roadmap.md`

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

## Contract draft

Route:

- `GET /v1/codex/usage/local`

Query params:

- `days` (optional integer, default `30`, clamped to `[1, 90]`)

Response shape:

```json
{
  "updated_at": 1712428800000,
  "days": [
    {
      "day": "2026-04-06",
      "input_tokens": 1200,
      "cached_input_tokens": 250,
      "output_tokens": 900,
      "total_tokens": 2100,
      "agent_time_ms": 450000,
      "agent_runs": 3
    }
  ],
  "totals": {
    "last7_days_tokens": 8800,
    "last30_days_tokens": 35210,
    "average_daily_tokens": 1257,
    "cache_hit_rate_percent": 19.4,
    "peak_day": "2026-04-03",
    "peak_day_tokens": 4200
  },
  "top_models": [
    {
      "model": "gpt-5.3-codex",
      "tokens": 22800,
      "share_percent": 64.7
    }
  ]
}
```

Error policy:

- Invalid `days` parses to default, not hard error.
- Scan failures return empty-but-valid snapshot shape if possible.
- Route should only return 5xx when service cannot initialize safely.

## Parser semantics to freeze

- Session root path:
  - resolve `CODEX_HOME` if defined
  - fallback to `~/.codex`
  - scan under `<codex_home>/sessions`
- File traversal:
  - day directories by `YYYY/MM/DD`
  - only `.jsonl` files
  - ignore unreadable files
- Event handling:
  - parse `event_msg` payloads with token usage
  - support both `total_token_usage` and `last_token_usage`
  - use delta logic to avoid double-counting totals
  - track agent run counts from assistant-message style events
  - track active time via timestamp deltas capped by max gap
- Model attribution:
  - prefer turn context model
  - fallback to token payload model fields
  - unknown model is excluded from top-model leaderboard

## Frontend behavior to freeze

- Route path: `/usage-snapshot`
- Screen states:
  - loading skeleton
  - loaded state
  - empty state
  - recoverable error banner with retry
- Refresh behavior:
  - initial load on mount
  - fixed interval polling
  - manual refresh button
  - stale-response guard with request generation id

## Test acceptance criteria to freeze

- Backend unit tests for parser edge cases and formulas.
- Backend integration test for route contract and days clamp.
- Frontend unit tests for screen render states and refresh behavior.
- Frontend unit test for sidebar button navigation.
- Frontend E2E test for full entrypoint flow and screen visibility.

## File-target plan for later phases

- Backend:
  - `backend/main.py`
  - `backend/routes/codex.py`
  - `backend/services/local_usage_snapshot_service.py` (new)
  - `backend/tests/unit/test_local_usage_snapshot_service.py` (new)
  - `backend/tests/integration/test_codex_api.py`
- Frontend:
  - `frontend/src/App.tsx`
  - `frontend/src/api/types.ts`
  - `frontend/src/api/client.ts`
  - `frontend/src/features/graph/Sidebar.tsx`
  - `frontend/src/features/graph/Sidebar.module.css`
  - `frontend/src/features/usage-snapshot/UsageSnapshotPage.tsx` (new)
  - `frontend/src/features/usage-snapshot/UsageSnapshotPage.module.css` (new)
  - `frontend/src/features/usage-snapshot/useLocalUsageSnapshot.ts` (new)
  - `frontend/tests/unit/Sidebar.test.tsx`
  - `frontend/tests/unit/UsageSnapshotPage.test.tsx` (new)
  - `frontend/tests/e2e/usage-snapshot.spec.ts` (new)

## Deliverables

- Contract checkpoint in this phase doc is complete and approved.
- Any open questions are logged in artifacts with explicit ownership and due date.

## Exit criteria

- API shape, parser semantics, UI states, and test matrix are frozen.
- No open product/architecture question blocks Phase 1.
