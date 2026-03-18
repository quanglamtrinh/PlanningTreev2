# Split Refactor Phase Docs

Last updated: 2026-03-17

## Rule

Do not bulk-generate phase files.

Create these files only when a phase actually starts:

- `PHASE_N_PLAN.md`
- `PHASE_N_PROGRESS.md`
- `PHASE_N_VALIDATION.md`

## When To Create Each File

- Create `PHASE_N_PLAN.md` when implementation planning for that phase begins and the work needs phase-local tasks, boundaries, or acceptance criteria beyond the master plan.
- Create `PHASE_N_PROGRESS.md` when active implementation for that phase begins and there is meaningful progress to record.
- Create `PHASE_N_VALIDATION.md` when the phase has concrete validation work, test runs, or signoff evidence to capture.

## Required Contents

### `PHASE_N_PLAN.md`

- phase goal
- in-scope changes
- out-of-scope boundaries
- implementation tasks
- acceptance checks
- open phase-local risks

### `PHASE_N_PROGRESS.md`

- dated progress entries
- notable changes landed
- blockers or scope changes
- remaining work

### `PHASE_N_VALIDATION.md`

- validation commands run
- test coverage touched
- manual checks performed
- failures, warnings, or residual risks
- final validation outcome

## Constraint

- No empty placeholder phase files.
- No pre-creation of `PHASE_1_*`, `PHASE_2_*`, and so on before the corresponding phase actually begins.
