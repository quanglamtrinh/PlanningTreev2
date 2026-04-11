# Phase 6 Stabilization Notes

Date: 2026-04-09.

Status: completed.

## Issues found and fixes

1. Invalid frontend test command in rollout doc
   - Severity: medium
   - Symptom: `npm run test --prefix frontend` fails because `frontend/package.json` has no `test` script.
   - Fix: replaced with valid commands:
     - `npm run test:unit --prefix frontend`
     - `npm run test:e2e --prefix frontend -- usage-snapshot.spec.ts`
2. Full-suite backend parity fixture mismatch
   - Severity: high (release-gate blocker)
   - Symptom: `test_conversation_v3_parity_fixtures` expected audit guidance item visibility that current projector intentionally hides.
   - Fix: updated `audit_explore_and_diff` fixture expectations to align with hidden audit guidance behavior.
3. Full-suite backend spec stale assertion drift
   - Severity: high (release-gate blocker)
   - Symptom: `test_spec_stale_detection` expected `spec_stale=True` but current workflow semantics mark `frame_branch_ready=True` and `spec_read_only=True`.
   - Fix: updated test assertions to current semantics (`frame_branch_ready`, `spec_read_only`, `spec_stale=False`).
4. Packaged validation freshness drift
   - Severity: medium
   - Symptom: `validate:build` failed freshness check after frontend rebuild.
   - Fix: rebuilt backend bundle with `python scripts/build-backend.py`, then `validate:build` passed.

## Stabilization watchpoints

1. Backend scan/cache behavior
   - Verified with temporary fixture smoke:
     - no sessions -> zero totals
     - moderate/large history -> non-zero totals and top models
     - repeat read within TTL -> identical `updated_at` (cache-hit proxy)
2. Frontend route and refresh failures
   - Verified non-blocking refresh-failure UX via `usage-snapshot.spec.ts`.
3. Existing usage sidebar regression
   - Covered in passing frontend unit suite (`Sidebar` tests included in full run).
4. Memory growth
   - No anomalous signal observed in short-run smoke; no long-duration soak was executed in this phase.

## Residual non-blocking notes

1. React Router future-flag warnings remain in unit test output.
2. `NodeDetailCard` act warnings remain in unit test output.
3. Vite chunk-size warning remains for frontend production build.
4. PyInstaller non-fatal hidden-import warnings remain in build output.

## Final stabilization decision

Phase 6 accepted. Feature is stable for closeout with no open blocker/high issue on the Usage Snapshot path.
