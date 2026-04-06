# Phase 1: Backend Scanner and API Foundation

Status: not started.

Effort: 22% (about 5.0 engineering days).

Depends on: Phase 0.

## Goal

Implement a production-ready baseline scanner and expose snapshot data through a stable backend API route.

## Scope

- Build local usage scanner service in backend.
- Add route contract `GET /v1/codex/usage/local`.
- Wire service lifecycle in FastAPI app state.
- Deliver baseline tests for parser and route.

## Detailed implementation checklist

## 1) Create service module

Create `backend/services/local_usage_snapshot_service.py` with:

- data containers:
  - `DailyTotals`
  - `UsageTotals`
- public service API:
  - `read_snapshot(days: int | None = None) -> dict[str, Any]`
- internal helpers:
  - day-key generation
  - sessions-root resolution
  - per-day directory resolution
  - scan-file parsing
  - token usage extraction
  - timestamp parsing and day bucketing
  - final snapshot assembly

## 2) Implement sessions-root and traversal

- resolve Codex home:
  - `CODEX_HOME` env if present and non-empty
  - else `Path.home() / ".codex"`
- sessions root:
  - `<codex_home>/sessions`
- traversal:
  - generate ordered day keys for requested window
  - scan `YYYY/MM/DD` dirs
  - include only `.jsonl` files

## 3) Implement parser semantics

- skip oversized lines (cap to prevent pathological memory spikes).
- parse JSON safely; continue on malformed lines.
- handle relevant entry forms:
  - `turn_context`
  - `event_msg`
  - `response_item`
- token aggregation:
  - detect `total_token_usage`
  - detect `last_token_usage`
  - maintain per-file previous totals to avoid double count
- run/time aggregation:
  - increment run count for assistant-message events
  - track active time by timestamp deltas with max-gap cap
- model totals:
  - derive model from turn context first, then token payload fallback

## 4) Build stable output snapshot

- include `updated_at` epoch milliseconds.
- include `days` in chronological order.
- include computed totals:
  - `last7_days_tokens`
  - `last30_days_tokens` (or selected-window total by contract)
  - `average_daily_tokens`
  - `cache_hit_rate_percent`
  - `peak_day`
  - `peak_day_tokens`
- include `top_models` sorted by descending token count.

## 5) Add API route

Update `backend/routes/codex.py`:

- add endpoint:
  - `@router.get("/codex/usage/local")`
- parse query param `days` and pass to service.
- return service snapshot directly as JSON.

## 6) Wire app state

Update `backend/main.py`:

- instantiate service once in `create_app`.
- assign to `app.state.local_usage_snapshot_service`.

## 7) Add baseline backend tests

Unit tests (`backend/tests/unit/test_local_usage_snapshot_service.py`):

- total-only token stream aggregation
- mixed last+total usage without double count
- assistant run counting
- active-time gap capping behavior
- malformed lines ignored safely
- top-model ordering and share percentages

Integration tests (`backend/tests/integration/test_codex_api.py`):

- route returns expected shape
- route honors `days` query

## File targets

- `backend/services/local_usage_snapshot_service.py` (new)
- `backend/routes/codex.py`
- `backend/main.py`
- `backend/tests/unit/test_local_usage_snapshot_service.py` (new)
- `backend/tests/integration/test_codex_api.py`

## Verification commands

- `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
- `python -m pytest backend/tests/integration/test_codex_api.py -q`

## Deliverables

- Stable snapshot route available at `/v1/codex/usage/local`.
- Baseline parser correctness proven in unit tests.
- Route contract validated in integration tests.

## Exit criteria

- Route works against real local `.codex/sessions` data.
- No blocker-level parser bug remains open.
- Phase 2 can proceed with performance and observability hardening.
