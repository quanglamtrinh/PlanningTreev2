# Phase 8 Plan: Test Evidence And Tracking Closeout

Last updated: 2026-03-18

## Phase Goal

- Close the remaining split-refactor checklist items with explicit test evidence.
- Add only the narrow test coverage still missing after auditing the current suite.
- Finish the split-refactor tracking artifacts without changing the split contract or runtime behavior.

## In-Scope Changes

- Audit the existing prompt-builder, split-contract, split-service, split API, and split rendering suites for direct evidence against the remaining Phase 8 checklist items.
- Reuse existing test evidence for `P8.1`-`P8.3` wherever it already provides direct proof.
- Add service-level proof for the Phase 3 invariant (`P8.4`) at the materialization layer.
- Add split-specific replace/supersede lifecycle proof for `P8.9`, split between backend state/history coverage and frontend replay/render coverage.
- Record an explicit Evidence Matrix and exact validation commands in the Phase 8 validation artifact.

## Out-Of-Scope Boundaries

- Public API, route, schema, or type changes.
- Split runtime behavior changes.
- Reopening current architecture docs unless validation reveals a real mismatch.
- Adding duplicate tests solely to mirror checklist wording when direct evidence already exists.

## Implementation Tasks

- Map `P8.1`-`P8.4` to concrete existing tests by file and test name before adding new coverage.
- Add one service-level test proving shared flat-family materialization behaves the same across canonical modes with the same output family.
- Add one replace lifecycle backend proof that covers confirm gating, revision 2, stable `split_metadata`, superseded vs active branch state, and persisted planning history.
- Add one split-specific frontend replay test proving the active replace branch renders canonical cards while the superseded branch renders through the replay UI path.
- Create Phase 8 tracking docs and update the checklist/progress artifacts once evidence and validation are complete.

## Acceptance Checks

- Every remaining unchecked checklist item is backed by an explicit test-evidence reference or a narrowly-scoped new test.
- `P8.4` is closed by service-level invariant proof, not only by prompt or validator tests.
- Replace lifecycle proof exists in both backend and frontend coverage without duplicating the same responsibility twice.
- Phase 8 validation records the exact commands used to prove the closeout.

## Open Phase-Local Risks

- Frontend render tests may continue to emit pre-existing React warnings; those do not block Phase 8 if the suite remains green.
- Validation should avoid broad repo-root frontend test commands that scan `.pytest_tmp` permission-denied directories.
