# Git Commit Rework - Phase 6-7 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-04.

Owner scope: rollout stabilization and cleanup closeout.

## 1. Goal and boundary recap

Phase 6 target:

- roll out commit metadata path safely and monitor correctness on new actions

Phase 7 target:

- remove temporary compatibility branches where approved and close track

Out of scope for this handoff:

- additional workflow feature expansion unrelated to commit metadata

## 2. Rollout checklist (Phase 6)

- [ ] stage rollout internal -> canary -> broad
- [ ] verify write behavior for new trigger actions only (no backfill)
- [ ] monitor:
  - [ ] missing `latestCommit` after eligible actions
  - [ ] unexpected mismatch between describe `head_sha` and workflow action outputs
  - [ ] idempotency/retry anomalies on review action
- [ ] document rollback steps

## 3. Cleanup checklist (Phase 7)

- [ ] remove temporary read fallback branches if no longer needed
- [ ] remove migration-only logs/guards added during rollout
- [ ] finalize docs with delivered architecture and residual risks
- [ ] publish closeout report

## 4. Expected write scope (planned)

- `backend/services/node_detail_service.py` (cleanup only, if approved)
- `backend/services/execution_audit_workflow_service.py` (cleanup only, if approved)
- `backend/services/split_service.py` (cleanup only, if approved)
- `backend/tests/*` and `docs/thread-rework/gitcommit/*`

## 5. Exit criteria for Phase 6-7

- rollout window completes without blocking regressions
- commit metadata is stable for all eligible new actions
- migration track is documented and handoff-ready
