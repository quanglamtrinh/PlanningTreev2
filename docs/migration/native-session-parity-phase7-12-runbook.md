# Native Session/Thread Parity — Full Rollout Runbook (Phase 7-12)

## Scope
- Full rollout, no canary.
- Legacy projected transcript fallback is removed after one-shot migration.
- Startup fails fast if any `legacy_adopted` binding remains unmigrated.

## Pre-Deployment
1. Backup `session_core_v2.sqlite3` and workspace `.planningtree` folders.
2. Deploy backend + frontend artifacts together (single rollout window).
3. Ensure `Session Core V2` endpoints are enabled for turns/events/requests.

## Deployment Sequence
1. Start backend.
2. Backend runs one-shot legacy transcript migration:
   - Finds workflow bindings with `createdFrom=legacy_adopted`.
   - Imports legacy snapshot transcript to native journal/turns.
   - Writes per-thread migration marker in `session_v2_legacy_migrations`.
3. Backend verifies there are no remaining unmigrated legacy bindings.
4. If any migration fails or remains pending, backend startup aborts.
5. Start frontend against upgraded backend.

## Post-Deployment Smoke
1. Start execution from idle and verify transcript streams immediately.
2. Reload UI during execution and verify replay/hydration consistency.
3. Open stream late and verify `turn/started` + transcript replay appears.
4. Complete execution and verify workflow settlement with matching `turnId`.
5. Run improve/audit/package-review flows and verify role->thread routing.
6. Simulate stream reconnect and verify no duplicate or missing deltas.
7. Validate `?debugSession=1` panel shows lane/thread/cursor/run diagnostics.

## Observability Signals
- Backend logs:
  - legacy migration summary and failures
  - settlement mismatch warnings
  - session stream open/drop guard logs
- Frontend debug telemetry events:
  - `session-v2-gap-metric`
  - `session-v2-correlation`

## Rollback
1. Roll back backend + frontend together.
2. Restore `session_core_v2.sqlite3` and `.planningtree` backups if required.
3. Re-run smoke checks on restored version.
