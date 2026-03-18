# Split Refactor Progress Log

Last updated: 2026-03-17

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 1 | completed | Registry and route guard landed with a temporary legacy route bridge |
| Phase 2 | pending | Prompt and schema refactor not started |
| Phase 3 | pending | Service output-family refactor not started |
| Phase 4 | pending | Fallback migration not started |
| Phase 5 | pending | Frontend registry and type migration not started |
| Phase 6 | pending | Split surface cleanup not started |
| Phase 7 | pending | Cutover cleanup not started |
| Phase 8 | pending | Tests and docs stabilization not started |

## Entries

### 2026-03-17

- Created the `docs/split-refactor/` scaffold.
- Added `MASTER_PLAN.md`, `DECISION_LOG.md`, `IMPLEMENTATION_CHECKLIST.md`, `PROGRESS_LOG.md`, `OPEN_ISSUES.md`, and `phases/README.md`.
- Locked the effort as a backend-first hard cutover to the 4 canonical modes and the shared `flat_subtasks_v1` output family.
- Preserved the rule that phase-specific docs must only be created when a phase actually starts.
- Started and completed Phase 1 with a canonical split registry, closed route parsing, and a temporary legacy route bridge for `walking_skeleton` and `slice`.
- Added targeted tests proving bad modes still return `400 invalid_request` and canonical new modes are guarded before the service is called.
