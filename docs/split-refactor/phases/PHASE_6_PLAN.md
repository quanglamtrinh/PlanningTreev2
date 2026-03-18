# Phase 6 Plan: Sole Split Surface Cleanup

Last updated: 2026-03-17

## Phase Goal

- Make the live split surface explicit and singular by keeping split creation in the `GraphNode` menu only.
- Remove dormant graph-side split affordances that no longer belong to the runtime product.
- Align current docs with the actual split flow without changing split contract behavior.

## In-Scope Changes

- Verify the unused legacy graph action panel has no runtime render path, no active import chain, and no barrel export.
- Delete the unused graph-side split panel component and stylesheet.
- Keep `GraphWorkspace`, `TreeGraph`, `GraphNode`, store wiring, API client wiring, and `confirm_replace` behavior unchanged.
- Update current docs so split creation is described through `GraphNode`, `GraphWorkspace`, `routes/split.py`, and the asynchronous planning flow.
- Add Phase 6 tracking docs and update the split-refactor checklist/progress artifacts.

## Out-Of-Scope Boundaries

- Backend API or route changes.
- Split schema, payload, or canonical mode changes.
- Legacy read-tolerance cleanup in persisted readers, history surfaces, or replay surfaces.
- Audit, migration, or other historical doc rewrites outside the current-doc set.

## Implementation Tasks

- Remove the unused graph-side split panel component and its stylesheet once dead-code verification is complete.
- Keep the `GraphNode` menu as the only UI entrypoint that can initiate canonical split creation.
- Update `docs/ARCHITECTURE.md` to describe the live split flow through `GraphNode`, `GraphWorkspace`, `project-store`, `api/client.ts`, `routes/split.py`, and `SplitService`.
- Update `docs/features/graph-workspace.md` so it documents the four canonical split actions and no longer describes legacy placeholder split affordances.
- Record Phase 6 completion in split-refactor tracking docs.

## Acceptance Checks

- No non-`GraphNode` UI path can initiate a canonical split.
- The unused graph-side split panel component and stylesheet no longer exist in live frontend source.
- Current docs describe split creation through the live `GraphNode` path rather than the removed placeholder surface.
- Existing graph-menu and planning-host tests still prove the sole split entrypoint model after cleanup.

## Open Phase-Local Risks

- Legacy read-tolerance code still uses old payload labels for transition readability; Phase 6 must not remove or alter that compatibility.
- Historical docs outside the current-doc scope may still describe pre-cleanup ownership and should not be treated as current guidance.
