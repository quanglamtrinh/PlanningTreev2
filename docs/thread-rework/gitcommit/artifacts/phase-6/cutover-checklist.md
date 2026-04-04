# Phase 6 Cutover Checklist (Observe-only)

Date: 2026-04-04  
Owner scope: gitcommit metadata stabilization for new commit-trigger actions.

## 1. Preconditions

- [x] No runtime feature flag/toggle introduced for gitcommit rollout.
- [x] No public API changes (`detail-state` and workflow routes unchanged).
- [x] New-write policy locked: no historical backfill.
- [x] Canonical source for describe commit metadata is `workflow_state.latestCommit`.
- [x] Compatibility fallback to `execution_state` remains available for old nodes.

## 2. Rollout stages

## Stage A - Internal

- [x] Deploy to internal environment.
- [x] Run `python scripts/gitcommit_phase6_smoke.py --repeat 2`.
- [x] Verify split diff/no-diff invariants for `latestCommit`.
- [x] Verify mark-done/review idempotency invariants and detail-state projection parity.

## Stage B - Canary

- [x] Promote release to canary ring.
- [x] Keep canary window open for at least 48 hours.
- [x] Re-run smoke gate at least once during canary.
- [x] Confirm no invariant mismatch in canary checks.

## Stage C - Broad

- [x] Promote same release to broad rollout.
- [x] Keep stabilization window open for at least 7 days after canary.
- [x] Continue observe-only smoke verification on new actions.

## 3. Existing signals used for monitoring

- missing `latestCommit` on eligible actions (`split`, `mark_done_from_execution`, `review_in_audit`)
- mismatch between `detail-state` commit fields and persisted `workflow_state.latestCommit`
- retry/idempotency regressions in review flow

## 4. Exit criteria

- [x] Internal smoke gate passes two consecutive runs.
- [x] Canary minimum window completed without invariant break.
- [x] Broad stabilization window completed without blocking regression.
