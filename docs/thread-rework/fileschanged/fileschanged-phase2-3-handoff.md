# FilesChanged Rework - Phase 2-3 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-03.

Owner scope: execution diff hydration and frontend renderer cutover.

## 1. Goal and boundary recap

Phase 2 target:

- hydrate per-file patch data for execution file-change items from worktree diff against run start sha

Phase 3 target:

- cut over execution fileChange UI to consume canonical per-file patch data and render line-level diffs

Out of scope for this handoff:

- full rollout gate enablement
- legacy-turn migration/backfill
- audit-lane adoption

## 2. Implementation checklist

- [ ] attach per-file patch text for new execution turns
- [ ] keep no-op behavior when structured diff already exists
- [ ] validate path-to-hunk matching and fallback behavior
- [ ] switch `FileChangeToolRow` primary source to canonical file-change entries
- [ ] ensure +/- counters come from real patch lines, not path-only placeholders
- [ ] keep temporary fallback for legacy turns without patch payload
- [ ] remove or isolate debug code that can cause re-render loops
- [ ] add frontend unit tests for single-file and multi-file expansion

## 3. Expected write scope (planned)

- `backend/services/execution_audit_workflow_service.py`
- `backend/services/git_checkpoint_service.py`
- `backend/tests/unit/test_execution_audit_workflow_service.py`
- `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/tests/unit/*fileChange*`
- `frontend/tests/unit/*MessagesV3*`

## 4. Acceptance evidence expected before closing Phase 2-3

- [ ] new execution turns show non-empty diff panels when files changed
- [ ] per-file expansion shows `+` / `-` lines and changed content
- [ ] card-level and row-level stats match parsed patch data
- [ ] no maximum-update-depth regressions in conversation feed
- [ ] no invalid SVG path warnings from file-change row icon controls

## 5. Risks to watch

- path matching misses when diff path format differs from emitted file path
- large diffs causing render performance regression
- fallback logic accidentally masking missing canonical payload on new turns

