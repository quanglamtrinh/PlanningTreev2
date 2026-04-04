# Git Commit Rework - Phase 4-5 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-04.

Owner scope: node-detail projection cutover and parity hardening.

## 1. Goal and boundary recap

Phase 4 target:

- make node-detail commit section read workflow-owned commit metadata first

Phase 5 target:

- lock behavior with unit/integration regression coverage

Out of scope for this handoff:

- rollout gating and environment stabilization (Phase 6)
- cleanup/removal work (Phase 7)

## 2. Read-path and API compatibility rules

- keep API response fields unchanged:
  - `initial_sha`
  - `head_sha`
  - `commit_message`
- read order for non-review nodes:
  1. workflow `latestCommit`
  2. fallback `execution_state`
- review nodes keep null commit fields

## 3. Implementation checklist (Phase 4-5)

- [ ] update `node_detail_service` to use new read order
- [ ] verify no break in existing describe consumers
- [ ] add integration tests:
  - split commit visible in parent describe
  - mark-done-execution commit visible
  - review-in-audit commit visible
  - no-diff action still shows planned message
- [ ] add fallback coverage when `latestCommit` missing

## 4. Expected write scope (planned)

- `backend/services/node_detail_service.py`
- `backend/tests/integration/*git*checkpoint*`
- `backend/tests/integration/*workflow*review*`
- `frontend/src/features/node/NodeDescribePanel.tsx` (only if display behavior needs adjustment)

## 5. Exit criteria for Phase 4-5

- node describe shows correct latest commit metadata for new actions
- compatibility fallback works for nodes without new metadata
- regression suite passes for split + execution + audit commit flows
