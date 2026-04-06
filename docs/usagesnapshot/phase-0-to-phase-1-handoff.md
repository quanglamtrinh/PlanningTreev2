# Usage Snapshot Phase 0 to Phase 1 Handoff

Status: ready for implementation.

Date: 2026-04-06.

Owner scope: transition from contract freeze to backend implementation kickoff.

## 1. Purpose of this handoff

Phase 0 is complete. This handoff freezes what Phase 1 implementers must treat as non-negotiable contract and clarifies exactly what to build next without reopening product decisions.

## 2. Phase 0 completion summary

Contract freeze is complete across:

- API contract (`GET /v1/codex/usage/local`)
- parser and aggregation semantics
- UI route and refresh behavior
- test acceptance matrix
- deferred scope guard

Tracker state:

- `docs/usagesnapshot/progress.yaml`
  - `status: phase_1_not_started`
  - `current_phase: 1`
  - phase 0 marked `completed`

## 3. Required reading order before coding

Read these docs in order before touching backend code:

1. `docs/usagesnapshot/phase-0-contract-freeze.md`
2. `docs/usagesnapshot/artifacts/phase-0-contract-checklist.md`
3. `docs/usagesnapshot/artifacts/phase-0-current-state-evidence.md`
4. `docs/usagesnapshot/artifacts/phase-0-test-acceptance-matrix.md`
5. `docs/usagesnapshot/phase-1-backend-scanner-and-api-foundation.md`

## 4. Locked contract decisions (do not reopen in Phase 1)

1. Usage Snapshot is a dedicated screen with route `/usage-snapshot`.
2. Screen is opened from a new sidebar button above existing usage block.
3. Data scope is all Codex sessions from Codex home; no workspace/project filter.
4. Backend route is `GET /v1/codex/usage/local`.
5. Query param `days` is optional, defaults to `30`, clamp range `[1, 90]`.
6. Invalid `days` input falls back to default `30` (not hard validation error).
7. Response remains snake_case and includes fixed keys:
   - `updated_at`
   - `days[]`
   - `totals`
   - `top_models[]`
8. Parser must support both `total_token_usage` and `last_token_usage`.
9. Delta logic must prevent double count when mixed usage payloads appear.
10. `agent_time_ms` uses timestamp deltas capped by `MAX_ACTIVITY_GAP_MS = 120000`.
11. Day bucket uses local timezone of backend host.
12. Model leaderboard excludes `unknown`, sorts descending by tokens, and keeps top 4.
13. Route should return valid empty snapshot on partial scan degradation where possible.
14. Usage snapshot refresh policy is polling + manual refresh; no SSE for this feature.

## 5. Phase 1 implementation scope (what to build now)

1. Add scanner service module:
   - `backend/services/local_usage_snapshot_service.py`
2. Add API endpoint in:
   - `backend/routes/codex.py`
3. Wire service in app lifecycle:
   - `backend/main.py`
4. Add backend unit coverage:
   - `backend/tests/unit/test_local_usage_snapshot_service.py`
5. Add backend integration coverage:
   - `backend/tests/integration/test_codex_api.py` (usage-local route cases)

Phase 1 stays backend-only. Frontend route/page/sidebar work starts in later phases.

## 6. Out-of-scope guardrails (must stay deferred)

Do not include these in Phase 1:

- workspace/project filter
- SSE/push channel for usage snapshot updates
- persistent aggregate DB/cache for long-term snapshots
- account widget redesign
- changes to existing `/v1/codex/account` and `/v1/codex/events` behavior

Reference: `docs/usagesnapshot/artifacts/phase-0-deferred-backlog.md`

## 7. Phase 1 acceptance bar

Implementation is accepted only when:

1. route returns stable snake_case snapshot shape for local data
2. parser handles malformed/oversized/unreadable inputs safely (skip and continue)
3. `days` semantics follow the locked contract exactly (default/clamp/fallback)
4. deterministic aggregation checks are green in unit tests
5. integration tests confirm route contract and degraded-input stability

Verification command families:

- `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
- `python -m pytest backend/tests/integration/test_codex_api.py -q`

## 8. Known risks and handling expectations

1. Risk: token double count from mixed `last` and `total` payloads.
   - Required handling: maintain per-file previous totals and explicit delta safeguards.
2. Risk: scan latency growth with large session history.
   - Required handling in Phase 1 baseline: deterministic day-bounded traversal and safe parsing.
   - Further optimization belongs to Phase 2.
3. Risk: silent parser failure masking regressions.
   - Required handling: explicit skip-safe behavior with measurable test coverage.

## 9. Open questions and blockers

No contract-level blockers remain for Phase 1 kickoff.

Any new request outside locked scope must be added to deferred backlog and must not expand Phase 1.

## 10. Handoff artifacts index

- `docs/usagesnapshot/phase-0-contract-freeze.md`
- `docs/usagesnapshot/artifacts/phase-0-current-state-evidence.md`
- `docs/usagesnapshot/artifacts/phase-0-contract-checklist.md`
- `docs/usagesnapshot/artifacts/phase-0-ui-state-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-test-acceptance-matrix.md`
- `docs/usagesnapshot/artifacts/phase-0-deferred-backlog.md`
- `docs/usagesnapshot/progress.yaml`

Phase gate outcome: Phase 0 PASS, Phase 1 READY.
