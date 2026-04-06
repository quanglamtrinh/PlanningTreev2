# Usage Snapshot Artifacts

Status: pending implementation.

This folder stores implementation evidence for the Usage Snapshot rollout.

## Expected artifact shape by phase

Phase 0:

- contract checklist
- parser rule examples
- open-questions log (if any)

Phase 1:

- backend API payload examples
- scanner parser unit-test evidence
- integration test notes for `/v1/codex/usage/local`

Phase 2:

- performance baselines
- cache hit/miss notes
- observability logging samples

Phase 3:

- frontend route and page screenshots
- polling behavior notes
- stale-response guard evidence

Phase 4:

- sidebar entrypoint screenshots
- route navigation checks
- accessibility checks

Phase 5:

- consolidated test matrix
- unit/integration/E2E run results
- flaky-test notes and resolutions

Phase 6:

- rollout checklist execution notes
- stabilization issues and fixes

Phase 7:

- closeout summary
- residual risk register
- ownership handoff notes

## Naming guidance

- Prefer `phase-<n>-<topic>.md` for notes.
- Prefer `.json` for machine-readable baselines.
- Keep each artifact focused on one verification objective.
