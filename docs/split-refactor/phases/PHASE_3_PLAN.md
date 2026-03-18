# Phase 3 Plan: SplitService Output-Family Refactor

Last updated: 2026-03-17

## Phase Goal

- Make `SplitService` canonical-capable internally without exposing canonical split execution through the public route yet.
- Move canonical split handling onto one shared `flat_subtasks_v1` materialization path while keeping the temporary legacy bridge intact for `walking_skeleton` and `slice`.

## In-Scope Changes

- Extend `backend/split_contract.py` with service-facing mode and output-family helpers.
- Add a runtime bundle helper so prompt building, validation, payload issues, and hidden retry feedback are selected consistently by mode.
- Refactor `backend/services/split_service.py` so canonical materialization branches by `output_family` rather than canonical mode string.
- Add a shared flat-family child materializer for canonical payloads using only `id`, `title`, `objective`, and `why_now`.
- Persist stable `split_metadata.output_family` and canonical materialization metadata after successful child creation.
- Block canonical fallback explicitly at the service layer until Phase 4.
- Add unit and integration coverage for service output-family selection, canonical flat materialization, fail-closed behavior, and legacy bridge regressions.

## Out-Of-Scope Boundaries

- Public canonical `/split` execution.
- Canonical deterministic fallback behavior.
- Frontend split mode, planning-event, or transport type migration.
- Removal of the temporary legacy route or service bridge.

## Implementation Tasks

- Add `ServiceSplitMode`, `ServiceSplitOutputFamily`, `FlatSubtaskItem`, `FlatSubtaskPayload`, and `split_output_family_for_mode(...)`.
- Add `split_runtime_bundle_for_mode(mode)` returning the full runtime helper set used by `SplitService`.
- Use canonical helpers for canonical modes and legacy helpers for bridge modes without any mixed-path fallback.
- Refactor `_apply_split_payload(...)` to branch by output family.
- Add `_create_flat_subtask_children(...)` and `_build_flat_subtask_description(...)`.
- Keep `_create_walking_skeleton_children(...)` and `_create_slice_children(...)` intact behind legacy output families.
- Persist `mode`, `output_family`, `source`, `warnings`, `created_child_ids`, `replaced_child_ids`, `created_at`, and `revision` on successful splits.
- Persist a stable canonical `materialized` record and optional debug-scoped raw payload for `flat_subtasks_v1`.
- Make canonical fallback raise an explicit guard instead of reusing legacy fallback logic.

## Acceptance Checks

- `SplitService` no longer branches directly on canonical mode strings to materialize canonical payloads.
- All canonical modes share the same `flat_subtasks_v1` apply path.
- Canonical paths fail closed and never use legacy validator, retry, or fallback helpers.
- Legacy bridge paths for `walking_skeleton` and `slice` continue to work unchanged.
- Route-level canonical guard remains `409 split_not_allowed`.

## Open Phase-Local Risks

- Canonical service execution is intentionally ahead of canonical route exposure, so direct service coverage must stay strong enough to protect the not-yet-public path.
- Legacy bridge code remains active by design and must still be removed in later cutover phases.
