# Git Commit Rework - Phase 4-5 Handoff

Status: implemented.

Date: 2026-04-04.

Owner scope: node-detail projection cutover and parity hardening.

## 1. Implemented behavior

- `node_detail_service` now resolves commit fields in this order for non-review nodes:
  1. `workflow_state.latestCommit`
  2. `execution_state` fallback
- API fields are unchanged:
  - `initial_sha`
  - `head_sha`
  - `commit_message`
- `task_present_in_current_workspace` now checks ancestry against the effective `head_sha` (workflow-first), so split-only commit metadata is respected in Describe.
- review node detail payload still returns null commit values.
- Describe reset buttons are now gated by:
  - checkpoint availability (`initial_sha` + `head_sha`)
  - task-present check
  - `execution_started == true`

## 2. Files changed in Phase 4-5

- `backend/services/node_detail_service.py`
- `backend/tests/integration/test_workflow_v2_review_thread_context.py`
- `backend/tests/unit/test_split_service.py`
- `frontend/src/features/node/NodeDescribePanel.tsx`
- `frontend/tests/unit/NodeDetailCard.test.tsx`

## 3. Completed checklist

- [x] cut node-detail read path to workflow-owned `latestCommit` first
- [x] keep backward-compatible fallback to `execution_state`
- [x] keep response shape stable for Describe consumers
- [x] ensure split commit metadata appears in parent Describe
- [x] ensure mark-done and review-in-audit commit metadata appears in Describe
- [x] ensure no-diff split commit still projects planned message + stable SHA pair
- [x] harden reset-button UX: disabled when execution has not started

## 4. Verification

Executed:

- `python -m pytest backend/tests/integration/test_workflow_v2_review_thread_context.py backend/tests/unit/test_split_service.py`
  - result: `13 passed`
- `npm run test:unit --prefix frontend -- tests/unit/NodeDetailCard.test.tsx`
  - result: `34 files passed`, `188 tests passed` (frontend unit suite script runs the full unit set)

## 5. Out-of-scope retained

- reset API semantics are unchanged in this phase (still execution-state-targeted endpoint behavior).
- no rollout gating/cleanup changes (Phase 6-7 scope).
