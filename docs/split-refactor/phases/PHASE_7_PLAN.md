# Phase 7 Plan: Cutover Cleanup And Convergence

Last updated: 2026-03-17

## Phase Goal

- Complete the hard cutover by removing legacy split-mode assumptions from the primary runtime path.
- Keep the live product on exactly the 4 canonical modes and the canonical `flat_subtasks_v1` split-result contract.
- Replace transitional history/replay rendering with canonical-only structured rendering plus a stable unsupported notice for legacy historical payloads.

## In-Scope Changes

- Remove internal legacy split executability and contract remnants from backend split runtime code.
- Canonicalize planning-thread bootstrap and planning-thread fork instructions.
- Tighten runtime-facing split-mode and split-metadata readers so legacy markers are normalized away at the read boundary.
- Make history/replay structured split rendering canonical-only and render a stable unsupported notice for legacy historical payloads.
- Update split-refactor tracking docs and validation artifacts for the Phase 7 cutover.

## Out-Of-Scope Boundaries

- Public `/split` route shape changes.
- Any remapping of `walking_skeleton` or `slice` to canonical modes.
- Restoring legacy history/replay cards as a supported product path.
- Reintroducing ad hoc compatibility parsing for legacy modes in runtime code.

## Implementation Tasks

- Remove legacy split runtime branches, legacy prompt/runtime helpers, and transitional contract aliases that no longer belong to the canonical runtime.
- Normalize legacy `planning_mode` to `null` at runtime read boundaries and drop legacy `split_metadata.mode` / `split_metadata.output_family` values from authoritative runtime readers.
- Keep canonical materialization and public route behavior unchanged for the 4 supported modes.
- Render structured split cards only for canonical materialization or valid canonical `flat_subtasks_v1` payloads; otherwise show the stable unsupported historical-format notice.
- Replace or update tests so canonical paths remain covered while legacy historical payloads now prove the unsupported fallback behavior.

## Acceptance Checks

- No primary-path runtime code assumes or exposes `walking_skeleton`, `slice`, `legacy_epic_phase`, or `legacy_flat_slice`.
- No planning thread is started or forked with base instructions that teach legacy split modes.
- No legacy `planning_mode` literal reaches frontend runtime state; legacy values are normalized to `null` at the read boundary.
- History/replay structured split rendering is canonical-only, and legacy historical split payloads render the unsupported notice.

## Open Phase-Local Risks

- Historical docs and narrowly scoped migration tests may still mention legacy labels; those references must not leak back into runtime code.
- If real user data reveals a migration blocker, it must be recorded explicitly rather than handled through new compatibility branches.
