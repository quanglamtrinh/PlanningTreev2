# Git Commit Rework - Phase 6-7 Handoff

Status: implemented.

Date: 2026-04-04.

Owner scope: rollout stabilization and cleanup closeout.

## 1. Scope locked for this handoff

- Phase 6: observe-only rollout stabilization for gitcommit metadata on new actions.
- Phase 7: cleanup hardening with compatibility fallback retained.
- No new runtime gate or API endpoint was introduced.
- No historical backfill; migration applies to new writes only.

## 2. Phase 6 completion (Observe-only rollout + stabilization)

Status: PASS

- Added runnable smoke gate script:
  - `scripts/gitcommit_phase6_smoke.py`
- Internal-stage gate is explicitly executable as two consecutive passes:
  - `python scripts/gitcommit_phase6_smoke.py --repeat 2`
- Rollout stages are fixed and documented:
  - internal
  - canary (minimum 48 hours)
  - broad (minimum 7 days after stable canary)
- Rollout monitoring uses existing workflow and test signals:
  - missing `latestCommit` for eligible actions
  - mismatch between `detail-state` commit fields and persisted `latestCommit`
  - review idempotency/retry regression signals
- Rollback policy remains release-level rollback (revert/deploy), not runtime toggles.

## 3. Phase 7 completion (Cleanup + closeout)

Status: PASS

- Added cleanup guard script:
  - `scripts/check_gitcommit_phase7_cleanup.py`
- Cleanup guard enforces:
  - split metadata remains workflow-owned (no `execution_state` write path)
  - describe read order keeps `latestCommit -> execution_state` fallback contract
  - `mark_done_from_audit` does not write `latestCommit`
  - key idempotency/regression tests remain present
- Compatibility fallback policy retained intentionally:
  - `node_detail_service` keeps fallback to `execution_state` when `latestCommit` is absent
  - no fallback removal in this cycle due to no-backfill policy

## 4. Test evidence

Backend targeted:

```bash
python -m pytest -q backend/tests/unit/test_workflow_state_store.py backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_split_service.py backend/tests/unit/test_node_detail_service_audit_v2.py
python -m pytest -q backend/tests/integration/test_workflow_v2_review_thread_context.py backend/tests/integration/test_git_checkpoint_integration.py
```

Front-end targeted:

```bash
npm run test:unit --prefix frontend -- tests/unit/NodeDetailCard.test.tsx
```

Operational checks:

```bash
python scripts/gitcommit_phase6_smoke.py --repeat 2
python scripts/check_gitcommit_phase7_cleanup.py
```

Latest local execution snapshot:

- backend targeted unit suites: `32 passed`
- backend targeted integration suites: `12 passed`
- frontend unit runner command: `34 files passed`, `188 tests passed`
- cleanup guard: PASS
- smoke script (`--repeat 1` local validation run): PASS

## 5. Artifacts

- `docs/thread-rework/gitcommit/artifacts/phase-6/cutover-checklist.md`
- `docs/thread-rework/gitcommit/artifacts/phase-6/smoke-results.md`
- `docs/thread-rework/gitcommit/artifacts/phase-6/rollback-notes.md`
- `docs/thread-rework/gitcommit/artifacts/phase-7/cleanup-checklist.md`
- `docs/thread-rework/gitcommit/artifacts/phase-7/closeout-summary.md`

## 6. Residual risks

- Legacy nodes without `latestCommit` still rely on fallback projection by design.
- Reset endpoint semantics remain out of scope for this track.
- Release discipline is required because rollback is release-level, not runtime-gated.
