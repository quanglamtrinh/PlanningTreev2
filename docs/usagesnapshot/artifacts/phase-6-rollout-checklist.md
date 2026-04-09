# Phase 6 Rollout Checklist

Date: 2026-04-09.

Status: completed.

## 1. Release candidate validation

1. Frontend production build
   - Command: `npm run build --prefix frontend`
   - Result: PASS
2. Packaged backend/runtime validation
   - Command: `npm run validate:build`
   - Initial result: FAIL (binary older than `frontend/dist`)
   - Remediation: `python scripts/build-backend.py`
   - Re-run result: PASS (`6 passed, 0 failed`)
3. Usage snapshot backend contract path
   - Command: `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py backend/tests/integration/test_codex_api.py -q`
   - Result: PASS (`26 passed`)
4. Usage snapshot UI flow
   - Command: `npm run test:e2e --prefix frontend -- usage-snapshot.spec.ts`
   - Result: PASS (`2 passed`)
5. Full release gate
   - Command: `npm run test`
   - Result: PASS (`frontend 36 files / 212 tests`, `backend 595 passed`)

## 2. Sidebar usage regression checks

1. Existing Session/Weekly/Credits rendering remains covered in `Sidebar` unit tests.
2. Full frontend unit run in `npm run test` includes `tests/unit/Sidebar.test.tsx` and passed.
3. Usage Snapshot placement is unchanged (under usage block in sidebar footer stack).

## 3. Data-shape scenario checks

Executed local smoke against `LocalUsageSnapshotService` using temporary `.codex/sessions` fixtures:

1. No sessions
   - Result: `EMPTY days= 7 total= 0`
2. Moderate history
   - Result: `MODERATE total= 2580 peak= 2026-04-08`
3. Large history (180 additional session files)
   - Result: `LARGE total= 69625 top_models= 2`
4. Cache-hit behavior under polling key reuse
   - Result: `CACHE same_updated_at= True`

## 4. Phase 6 sign-off

1. No blocker/high issue remains on Usage Snapshot feature path.
2. Full-suite gate is green after findings remediation.
3. Phase 6 exit criteria met.
