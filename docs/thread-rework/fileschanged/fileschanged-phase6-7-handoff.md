# FilesChanged Rework - Phase 6-7 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-03.

Owner scope: rollout stabilization and hard cleanup.

## 1. Goal and boundary recap

Phase 6 target:

- roll out migrated file-change path safely with gate control and monitoring

Phase 7 target:

- remove transitional legacy dependencies and close migration track

Out of scope for this handoff:

- additional product-scope changes outside file-change migration

## 2. Rollout checklist (Phase 6)

- [ ] add/enable execution file-change migration gate
- [ ] stage rollout internal -> canary -> broad
- [ ] confirm gate applies only to new turns
- [ ] monitor key signals:
  - [ ] empty-diff cards on new turns
  - [ ] render exceptions in file-change row
  - [ ] mismatch between emitted changed files and rendered rows
- [ ] prepare documented rollback procedure

## 3. Cleanup checklist (Phase 7)

- [ ] remove temporary fallback branches no longer needed for active turns
- [ ] remove migration-only telemetry/debug logs
- [ ] remove obsolete contract fields where approved
- [ ] finalize docs with final architecture and ownership
- [ ] publish closeout report and residual risk notes

## 4. Expected write scope (planned)

- `frontend/src/features/conversation/components/*`
- `frontend/src/features/conversation/state/*`
- `backend/conversation/projector/*`
- `backend/conversation/domain/*`
- `backend/tests/*` and `frontend/tests/*` cleanup updates
- `docs/thread-rework/fileschanged/*`

## 5. Acceptance evidence expected before closing Phase 6-7

- [ ] rollout window completes without blocking regressions
- [ ] new-turn file-change behavior is stable and observable
- [ ] no operational dependency remains on legacy execution file-change rendering path
- [ ] migration docs are complete and handoff-ready

