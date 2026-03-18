# Phase 5 Plan: Frontend Canonical Split Migration And Public Route Flip

Last updated: 2026-03-17

## Phase Goal

- Make canonical split usable end to end by opening the public `/split` route for the 4 canonical modes and moving frontend create-paths to canonical-only mode selection.
- Keep frontend read paths tolerant of legacy split history and persisted legacy planning-mode values during the transition window.

## In-Scope Changes

- Open `/split` for `workflow`, `simplify_workflow`, `phase_breakdown`, and `agent_breakdown`.
- Reject public `walking_skeleton` and `slice` inputs with the existing `400 invalid_request` behavior.
- Add a frontend split registry and use it to render GraphNode split actions dynamically.
- Move `TreeGraph`, `GraphWorkspace`, `project-store`, and the API client to canonical `SplitMode` create-path typing.
- Keep `NodeRecord.planning_mode` and `PlanningEvent.mode` tolerant enough to read legacy values while `SplitAcceptedResponse.mode` becomes canonical-only.
- Remove split actions from `PlanningConversationPanel` so GraphNode is the only exposed split entrypoint.
- Add shared split-payload normalization so conversation renderers can show canonical flat subtasks while still reading legacy split payloads.

## Out-Of-Scope Boundaries

- Removing the internal backend legacy bridge.
- GraphControls placeholder cleanup.
- Persisted-record migration or replay cleanup.
- Full legacy assumption cleanup across every secondary UI or history surface.

## Implementation Tasks

- Close the public route contract over the 4 canonical modes and remove the temporary canonical route guard.
- Add `SplitMode`, `LegacySplitMode`, and `ReadableSplitMode` frontend types.
- Create a frontend split registry for GraphNode menu rendering.
- Replace hardcoded `walking_skeleton` and `slice` wiring in `GraphNode`, `TreeGraph`, and `GraphWorkspace`.
- Update `api.splitNode` and `project-store.splitNode` to accept only canonical `SplitMode`.
- Preserve legacy read tolerance in `planning_mode`, planning events, and split payload rendering.
- Remove PlanningConversationPanel split buttons and point users to the graph node menu.
- Add frontend and backend coverage for canonical route acceptance, canonical create paths, and legacy read compatibility.

## Acceptance Checks

- Public `/split` accepts the 4 canonical modes and no longer accepts legacy modes.
- GraphNode is the only exposed split entrypoint in the UI.
- Frontend create paths no longer send `walking_skeleton` or `slice`.
- Canonical `split_result` payloads render correctly in conversation surfaces.
- Legacy split history and persisted legacy read paths still render without blocking rollout.

## Open Phase-Local Risks

- Legacy read compatibility still exists after public cutover, so later cleanup phases must avoid accidentally expanding that tolerance back into creation paths.
- GraphControls placeholder cleanup is intentionally deferred and still needs an explicit follow-up phase.
