# Usage Snapshot Phase 2 to Phase 3 Handoff

Status: ready for Phase 3 implementation.

Date: 2026-04-06.

Owner scope: transition from backend hardening to frontend route/screen/polling delivery.

## 1. Purpose of this handoff

Phase 2 is completed and validated. This handoff locks the backend performance and observability behaviors that Phase 3 must consume without reopening backend contract decisions.

## 2. Phase 2 delivery summary

Phase 2 goals were to harden `GET /v1/codex/usage/local` for polling traffic and improve diagnosability while keeping API response contract unchanged.

Delivered:

1. Cache + single-flight in local usage service:
   - `backend/services/local_usage_snapshot_service.py`
   - TTL: `30s`
   - cache key: `(normalized_days, resolved_sessions_root_path)`
   - process-local single-flight dedupe for same cache key
2. Days normalization centralized in service:
   - service accepts raw `days` and applies default/clamp/fallback
   - route now passes raw query value directly
   - `backend/routes/codex.py`
3. Structured diagnostics and summary logs:
   - counters: `files_visited`, `files_opened`, `files_skipped_unreadable`, `lines_total`, `lines_invalid_json`, `lines_oversized`, `token_events_applied`, `scan_duration_ms`, `cache_hit`
   - one summary log per request path:
     - cache hit: debug
     - cache miss/recompute: info
4. Test expansion for cache/concurrency and API boundaries:
   - `backend/tests/unit/test_local_usage_snapshot_service.py`
   - `backend/tests/integration/test_codex_api.py`

## 3. Contract conformance checklist (Phase 2)

All locked Phase 2 requirements are satisfied:

1. Public API shape for `/v1/codex/usage/local` is unchanged.
2. No new route or query parameter added.
3. Invalid `days` input still falls back to default (`30`) and does not 422.
4. Clamp behavior remains enforced at API behavior level:
   - `days=0` -> `1`
   - `days=-1` -> `1`
   - `days=999` -> `90`
   - `days=abc` -> `30`
5. Parser guardrails remain intact:
   - malformed JSON and oversized lines are skipped safely
   - unreadable files are skipped safely
6. Token aggregation semantics remain intact:
   - non-negative delta behavior preserved
   - mixed `total` + `last` streams do not double-count

## 4. Verification evidence

Executed commands:

1. `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
   - result: `15 passed in 0.73s`
2. `python -m pytest backend/tests/integration/test_codex_api.py -q`
   - result: `10 passed in 2.58s`

New/expanded checks added in Phase 2:

1. cache hit within TTL avoids re-scan.
2. stale cache after TTL recomputes.
3. concurrent same-key requests compute once (single-flight).
4. cache-key isolation by `days`.
5. cache-key isolation by sessions root path.
6. API-level `days` boundary and invalid-string fallback behavior.

## 5. Out-of-scope items intentionally deferred to Phase 3+

Not part of Phase 2 by design:

1. frontend `/usage-snapshot` route and screen.
2. sidebar entry button wiring for navigation.
3. frontend polling and manual refresh UX.
4. E2E coverage for the full page flow.
5. metrics endpoint/export beyond summary logging.

## 6. Phase 3 kickoff guidance

Phase 3 should integrate frontend against the now-stable backend behavior:

1. add frontend route `/usage-snapshot`.
2. build dedicated Usage Snapshot page UI.
3. implement polling + manual refresh client flow.
4. consume `/v1/codex/usage/local` without changing backend schema.
5. keep all-sessions scope (no workspace filter).

Recommended validation loop for Phase 3:

1. keep backend usage tests green while integrating frontend.
2. add frontend unit tests for API data mapping and polling behavior.
3. add route navigation/smoke checks before Phase 4 sidebar polish.

## 7. Risks and assumptions to carry forward

1. Cache is process-local by design and sufficient for current desktop single-backend runtime.
2. Snapshot staleness up to `30s` is accepted for polling use case in this rollout.
3. Diagnostics are log-only in Phase 2; there is no metrics endpoint yet.
4. Any request for workspace-specific filtering remains out of this migration scope.

## 8. Open blockers and questions

No blocking issues remain for Phase 3 kickoff.

## 9. Handoff artifact index

- `docs/usagesnapshot/phase-2-backend-performance-and-observability.md`
- `docs/usagesnapshot/phase-2-to-phase-3-handoff.md`
- `docs/usagesnapshot/phase-3-frontend-route-screen-and-polling.md`
- `docs/usagesnapshot/progress.yaml`

Phase gate outcome: Phase 2 PASS, Phase 3 READY.
