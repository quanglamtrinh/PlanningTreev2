# Phase 07 - State Shape and Hot Path Cleanup

Status: Completed (all P07 gates passed with committed evidence).

Scope IDs: C02, C03, C04.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Continues CodexMonitor-style state architecture hardening on top of stable stream behavior.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Hot-path patches cannot trigger global sort unless order changes.
- Structural sharing guarantees are mandatory for unchanged branches.
- State operations must remain compatible with downstream virtualization requirements.


## Objective

Lower per-event apply cost by normalizing conversation state, removing avoidable sort work, and enforcing structural sharing.

## Prerequisite

Phase 06 completed (all `P06` gates pass with committed evidence).

Reference handoff:

- `docs/render/phases/phase-06-frame-batching-fast-append/handoff-to-phase-07.md`.

Phase 07 entry artifact (`normalized_state_shape_frozen`):

- `docs/render/phases/phase-07-state-shape-hot-path/normalized-state-shape-v1.md`.

Preflight baseline and evidence conventions:

- `docs/render/phases/phase-07-state-shape-hot-path/evidence/baseline-manifest-v1.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_benchmark.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_trace.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/reducer_identity_tests.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/phase07-gate-report.json`.

Pre-phase-8 hardening note:

- Phase 07 gate closure now requires candidate-backed source evidence (`evidence_mode="candidate"`, `gate_eligible=true`).
- Synthetic evidence is allowed only for local dry-run and cannot be used for gate closure.

Closeout artifacts:

- `docs/render/phases/phase-07-state-shape-hot-path/close-phase-v1.md`.
- `docs/render/phases/phase-07-state-shape-hot-path/handoff-to-phase-08.md`.

## In Scope

1. C02: Normalized conversation state model.
2. C03: Remove sort on patch hot path.
3. C04: Strong structural sharing guarantees.

## Detailed Improvements

### 1. Normalized data model (C02)

Move toward:

- `itemsById`
- `orderedItemIds`
- `uiSignals` (non-conversation state)

Benefits:

- cheaper targeted updates
- less allocation churn
- easier selector scoping

### 2. Sort only when order changes (C03)

Avoid list sort for content-only patch updates:

- sort on insert/reorder operations only
- skip sort for append/edit metadata changes

### 3. Structural sharing policy (C04)

Guarantee unchanged branches keep same object identity so memoized selectors/components can skip rerender.

## Implementation Plan

1. Refactor apply function to normalized operations.
2. Introduce explicit operation types (insert, reorder, patch-content, patch-meta).
3. Add identity-preservation checks in reducer tests.

## Quality Gates

1. Performance:
   - lower apply duration p95/p99 on patch-heavy streams.
2. Render stability:
   - fewer component updates per event.
3. Correctness:
   - item order remains accurate after mixed operations.

## Test Plan

1. Unit tests:
   - normalization and reorder correctness.
   - structural sharing identity assertions.
2. Integration tests:
   - mixed insert/patch/reorder stream sequence.
3. Manual checks:
   - no regression in thread display ordering.

## Risks and Mitigations

1. Risk: migration bugs between old/new state shape.
   - Mitigation: compatibility adapter during transition.
2. Risk: hidden order assumptions in UI code.
   - Mitigation: explicit helper APIs for order access.

## Handoff to Phase 08

Once state shape is efficient, splitting stores and narrowing selectors has higher confidence and lower migration risk.


## Effort Estimate

- Size: Large
- Estimated duration: 5-7 engineering days
- Suggested staffing: 1 frontend primary + 1 frontend reviewer
- Confidence level: Medium (depends on current code-path complexity and test debt)





