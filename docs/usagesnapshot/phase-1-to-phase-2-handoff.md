# Usage Snapshot Phase 1 to Phase 2 Handoff

Status: ready for Phase 2 implementation.

Date: 2026-04-06.

Owner scope: transition from backend foundation delivery to backend hardening and observability.

## 1. Purpose of this handoff

Phase 1 is completed and validated. This handoff locks what has been shipped, what remains intentionally deferred, and how to start Phase 2 without reopening Phase 1 decisions.

## 2. Phase 1 delivery summary

Phase 1 goals were to ship backend baseline for local usage snapshot with stable API contract and test coverage that unblocks frontend integration later.

Delivered:

1. New backend scanner service:
   - `backend/services/local_usage_snapshot_service.py`
2. New API route:
   - `GET /v1/codex/usage/local`
   - `backend/routes/codex.py`
3. App-state wiring:
   - `backend/main.py`
4. Unit coverage:
   - `backend/tests/unit/test_local_usage_snapshot_service.py`
5. Integration coverage:
   - `backend/tests/integration/test_codex_api.py`
6. Docs wording alignment for `last30_days_tokens` semantics:
   - `docs/usagesnapshot/phase-1-backend-scanner-and-api-foundation.md`

## 3. Contract conformance checklist (Phase 1)

All locked Phase 1 contract items are implemented and verified:

1. Route exists: `GET /v1/codex/usage/local`.
2. `days` param behavior:
   - optional
   - invalid parse falls back to `30` (no 422)
   - clamped to `[1, 90]`
3. Response shape is fixed snake_case:
   - `updated_at`
   - `days[]`
   - `totals`
   - `top_models[]`
4. Parser semantics:
   - supports both `total_token_usage` and `last_token_usage`
   - uses per-file `previous_totals` to avoid double counting
   - skips malformed JSON lines safely
   - skips oversized lines safely
   - skips unreadable `.jsonl` files safely
5. Aggregation semantics:
   - `agent_runs` from assistant response events / agent message events
   - `agent_time_ms` from timestamp deltas with max gap `120000`
   - day bucket by backend host local timezone
6. Model leaderboard:
   - prefer turn-context model, fallback token payload model
   - exclude `unknown`
   - sort descending and truncate top 4
7. Totals semantics:
   - `last7_days_tokens` over most recent 7 days in selected window
   - `last30_days_tokens` over most recent max 30 days in selected window
   - `average_daily_tokens` rounded over same 7-day set
   - `cache_hit_rate_percent` rounded to 1 decimal
   - `peak_day` and `peak_day_tokens` computed in selected window
8. Route remains resilient under degraded input and returns valid snapshot shape.

## 4. Verification evidence

Executed commands:

1. `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
   - result: `10 passed in 0.49s`
2. `python -m pytest backend/tests/integration/test_codex_api.py -q`
   - result: `7 passed in 1.13s`

Test coverage highlights shipped in Phase 1:

1. total-only aggregation.
2. mixed `last + total` without double-count.
3. `last` deltas between totals.
4. malformed/oversized/unreadable input handling.
5. assistant run counting.
6. activity gap cap.
7. model attribution + leaderboard ordering/truncation.
8. days default/clamp behavior.
9. API shape + days behavior + degraded-input integration behavior.

## 5. Out-of-scope items intentionally deferred to Phase 2+

Not part of Phase 1 by design:

1. in-memory cache and TTL for usage snapshots.
2. concurrency lock to dedupe concurrent recomputation.
3. structured diagnostics/observability logs for scanner metrics.
4. additional perf validation under large session histories.
5. frontend route/page/sidebar/polling integration (starts in later phases).

## 6. Phase 2 kickoff guidance

Phase 2 implementation should focus on hardening without breaking the frozen API contract:

1. add cache key by `days`, with TTL and safe invalidation.
2. add lock-safe cache mutation and avoid duplicate concurrent scans.
3. add scan diagnostics counters and summary logs per request.
4. keep route output contract unchanged.
5. extend tests for cache hit/miss, stale refresh, and concurrency behavior.

Suggested validation loop for Phase 2:

1. run unit tests:
   - `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
2. run codex integration tests:
   - `python -m pytest backend/tests/integration/test_codex_api.py -q`
3. add targeted perf/degradation test cases before marking Phase 2 complete.

## 7. Risks to watch during Phase 2

1. cache staleness hiding recent usage changes.
2. race conditions around concurrent requests and cache refresh.
3. noisy logging volume if per-line parse logging is added accidentally.
4. accidental contract drift in `totals` semantics or `days` fallback behavior.

## 8. Open blockers and questions

No Phase 1 blockers remain for Phase 2 kickoff.

Any request that changes response contract or adds workspace filtering must be treated as out-of-scope and deferred to follow-up backlog.

## 9. Handoff artifact index

- `docs/usagesnapshot/phase-1-backend-scanner-and-api-foundation.md`
- `docs/usagesnapshot/phase-1-to-phase-2-handoff.md`
- `docs/usagesnapshot/phase-2-backend-performance-and-observability.md`
- `docs/usagesnapshot/progress.yaml`

Phase gate outcome: Phase 1 PASS, Phase 2 READY.
