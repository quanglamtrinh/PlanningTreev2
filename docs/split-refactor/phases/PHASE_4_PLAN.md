# Phase 4 Plan: Canonical Deterministic Fallback

Last updated: 2026-03-17

## Phase Goal

- Complete canonical split execution inside the backend service layer by replacing the Phase 3 fallback guard with deterministic fallback for all 4 canonical modes.
- Keep the public `/split` route unchanged so canonical modes remain route-guarded while the legacy bridge continues to run.

## In-Scope Changes

- Add a dedicated canonical fallback module at `backend/services/canonical_split_fallback.py`.
- Define deterministic fallback builders for `workflow`, `simplify_workflow`, `phase_breakdown`, and `agent_breakdown`.
- Make canonical fallback emit the same typed `flat_subtasks_v1` payload contract used by canonical parse and validation.
- Revalidate fallback payloads before they enter the shared canonical flat-family apply path.
- Preserve machine-readable fallback warnings and stable canonical materialization metadata.
- Add unit and service coverage for fallback semantics, execution order, and route-unchanged behavior.

## Out-Of-Scope Boundaries

- Public canonical `/split` execution.
- Frontend split mode exposure, transport types, or planning-event type migration.
- Removal of the legacy route or service bridge.
- Persisted-record migration or replay cleanup.

## Implementation Tasks

- Add a mode-dispatch canonical fallback helper plus 4 mode-specific builders.
- Keep fallback generation outside `SplitService` and call it only after canonical parse, validation, and retry handling finish.
- Revalidate fallback payloads with the same canonical validator used for model output.
- Keep canonical fallback on the shared `flat_subtasks_v1` apply path introduced in Phase 3.
- Preserve legacy fallback behavior for `walking_skeleton` and `slice`.
- Persist `source = "fallback"`, `output_family = "flat_subtasks_v1"`, `fallback_used`, and stable canonical `materialized` metadata on successful canonical fallback splits.

## Acceptance Checks

- Canonical modes no longer raise the Phase 3 fallback guard.
- All 4 canonical modes have deterministic fallback returning valid typed `flat_subtasks_v1` payloads.
- Canonical fallback runs only after canonical parse, validation, and retry handling complete.
- Fallback payloads are validated again before materialization.
- Public route behavior remains unchanged and canonical route requests still return `409 split_not_allowed`.
- Legacy bridge execution and fallback continue to work.

## Open Phase-Local Risks

- Canonical fallback is backend-complete before public exposure, so service-level coverage must stay strong enough to protect the not-yet-routed canonical path.
- Legacy bridge code remains active by design and must still be removed in later cutover phases.
