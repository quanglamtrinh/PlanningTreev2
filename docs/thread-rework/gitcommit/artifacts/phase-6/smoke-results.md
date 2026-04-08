# Phase 6 Smoke Results

Date: 2026-04-04  
Window: post-cutover observe-only validation.

## Automated smoke evidence

Smoke gate script:

```bash
python scripts/gitcommit_phase6_smoke.py --repeat 2
```

Result:

- PASS: two consecutive full smoke iterations
- PASS: split diff/no-diff latestCommit projection
- PASS: mark-done/review latestCommit write-path invariants
- PASS: review retry idempotency invariants
- PASS: detail-state projection parity with `latestCommit`

Targeted backend suites:

```bash
python -m pytest -q backend/tests/unit/test_workflow_state_store.py backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_split_service.py backend/tests/unit/test_node_detail_service_audit_v2.py
python -m pytest -q backend/tests/integration/test_workflow_v2_review_thread_context.py backend/tests/integration/test_git_checkpoint_integration.py
```

Result:

- PASS: targeted unit suites (`32 passed`)
- PASS: targeted integration suites (`12 passed`)

Targeted frontend suite:

```bash
npm run test:unit --prefix frontend -- tests/unit/NodeDetailCard.test.tsx
```

Result:

- PASS: `NodeDetailCard` + dependent unit matrix in frontend test runner (`34 files`, `188 tests`)

## Manual smoke matrix

| Scenario | Expected | Result |
|---|---|---|
| Split with diff | `latestCommit.committed=true`, describe shows split commit metadata on parent | PASS |
| Split with no diff | `latestCommit.committed=false`, `headSha==initialSha`, message persisted | PASS |
| Mark Done from Execution | `latestCommit` written with action source and parity in describe | PASS |
| Review in Audit + retry | retry reuses existing cycle/sha and keeps `latestCommit` stable | PASS |
| Mark Done from Audit | no new `latestCommit` overwrite; accepted sha progresses node | PASS |
| Legacy fallback | describe reads `execution_state` when `latestCommit` missing | PASS |

## Notes

- Rollout remains observe-only; no runtime gate introduced.
- Existing unrelated frontend warning noise is non-blocking for this track.
