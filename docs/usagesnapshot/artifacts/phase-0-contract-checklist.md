# Phase 0 Contract Checklist

Status: completed.

## Decision checklist (must all be locked)

| ID | Decision | Locked | Source |
|---|---|---|---|
| `dedicated_usage_snapshot_screen` | Usage Snapshot is a dedicated screen. | yes | `docs/usagesnapshot/phase-0-contract-freeze.md` |
| `sidebar_button_entrypoint` | Entry point is a button above existing sidebar usage block. | yes | `docs/usagesnapshot/phase-0-contract-freeze.md` |
| `all_codex_sessions_scope` | Aggregate all Codex sessions from Codex home. | yes | `docs/usagesnapshot/phase-0-contract-freeze.md` |
| `polling_refresh_strategy` | Frontend refresh uses polling + manual refresh. | yes | `docs/usagesnapshot/phase-0-contract-freeze.md` |
| `full_delivery_scope` | Delivery includes backend + frontend + automated tests incl. E2E. | yes | `docs/usagesnapshot/phase-0-contract-freeze.md` |

## API contract checklist

- [x] Route locked: `GET /v1/codex/usage/local`
- [x] `days` query semantics locked (default `30`, clamp `[1, 90]`, invalid -> default)
- [x] Response uses snake_case fields only
- [x] Response contains `updated_at`, `days[]`, `totals`, `top_models[]`
- [x] Error policy locked (skip malformed/oversized/unreadable safely; prefer valid empty snapshot fallback)

## Parser contract checklist

- [x] `CODEX_HOME` -> fallback `~/.codex` root policy locked
- [x] Day directory traversal (`YYYY/MM/DD`) locked
- [x] `.jsonl`-only file policy locked
- [x] `total_token_usage` + `last_token_usage` dual support locked
- [x] Delta rule to prevent double count locked
- [x] `agent_runs` event rule locked
- [x] `agent_time_ms` gap cap (`120000`) locked
- [x] Local timezone day-bucket rule locked

## Totals and leaderboard contract checklist

- [x] `last7_days_tokens` semantics locked
- [x] `last30_days_tokens` semantics locked
- [x] `average_daily_tokens` semantics locked
- [x] `cache_hit_rate_percent` formula + rounding locked
- [x] `peak_day` and `peak_day_tokens` semantics locked
- [x] Model ranking and truncation rules locked (`unknown` excluded, top 4, 1-decimal share)

## Frontend contract checklist

- [x] Route path locked: `/usage-snapshot`
- [x] UI state set locked: loading, loaded, empty, recoverable error
- [x] Stale-response guard requirement locked
- [x] No usage-SSE in this track locked

## Test contract checklist

- [x] Backend unit test categories locked
- [x] Backend integration contract checks locked
- [x] Frontend unit checks locked
- [x] Frontend E2E flow locked

## Phase gate checklist

- [x] No `TBD` remains in contract sections.
- [x] Scope guard for deferred items recorded.
- [x] Tracker can advance from Phase 0 to Phase 1.
