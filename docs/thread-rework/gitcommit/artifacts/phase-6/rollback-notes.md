# Phase 6 Rollback Notes (Release-level)

Date: 2026-04-04

## Rollback model

Observe-only rollout uses release rollback, not runtime feature toggles.

## Trigger conditions

- missing `latestCommit` detected for eligible new actions
- mismatch between `detail-state` commit projection and persisted `workflow_state.latestCommit`
- idempotency/retry regressions causing unstable review commit metadata

## Rollback procedure

1. Identify offending release SHA and affected environment ring.
2. Revert release commit set (or redeploy last known good release artifact).
3. Deploy rollback artifact through standard release pipeline.
4. Validate rollback with minimum smoke:
   - split diff/no-diff scenarios pass
   - mark-done/review parity checks pass
   - no commit-projection mismatches in describe
5. Record rollback event in release log and migration tracker.

## Post-rollback follow-up

- isolate regression with targeted unit/integration reproduction
- add explicit regression guard test
- re-run internal -> canary -> broad sequence after patch-forward
