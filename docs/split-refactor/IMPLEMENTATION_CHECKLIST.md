# Split Refactor Implementation Checklist

Last updated: 2026-03-17

Legend:

- `[ ]` not started
- `[~]` in progress
- `[x]` complete

## Phase 1 - Registry And Route Contract

- [x] `P1.1` Add canonical split registry for the 4 supported modes.
- [x] `P1.2` Encode `output_family`, `min_items`, `max_items`, UI visibility, and creation policy in the registry.
- [x] `P1.3` Add route-facing supported-mode adapter or parser for `backend/routes/split.py`.
- [x] `P1.4` Preserve `400 invalid_request` semantics for bad modes after closing the route contract.
- [x] `P1.5` Remove old `walking_skeleton` and `slice` from the supported route contract.

## Phase 2 - Prompt And Schema Refactor

- [x] `P2.1` Refactor `backend/ai/split_prompt_builder.py` to registry-driven prompt builders.
- [x] `P2.2` Add shared flat-schema example for `flat_subtasks_v1`.
- [x] `P2.3` Add shared parser for `subtasks[{id,title,objective,why_now}]`.
- [x] `P2.4` Add shared validator that rejects extra keys and old legacy keys.
- [x] `P2.5` Move hidden retry feedback to the shared flat-schema contract.
- [x] `P2.6` Remove legacy-mode parsing paths from the main split contract.

## Phase 3 - Service Output-Family Refactor

- [x] `P3.1` Refactor `SplitService` to branch by `output_family`, not by mode string.
- [x] `P3.2` Enforce the Phase 3 invariant that new-mode materialization depends only on `output_family` and the shared flat contract.
- [x] `P3.3` Add flat-family child creation path with one child per subtask.
- [x] `P3.4` Build child title from `title`.
- [x] `P3.5` Build child description from `objective + why_now`.
- [x] `P3.6` Persist stable materialization metadata in `split_metadata`.
- [x] `P3.7` Store raw item payload only under a debug-scoped metadata key if needed.

## Phase 4 - Deterministic Fallback Migration

- [x] `P4.1` Replace deterministic fallback for `workflow`.
- [x] `P4.2` Replace deterministic fallback for `simplify_workflow`.
- [x] `P4.3` Replace deterministic fallback for `phase_breakdown`.
- [x] `P4.4` Replace deterministic fallback for `agent_breakdown`.
- [x] `P4.5` Ensure fallback always emits the same `flat_subtasks_v1` contract as model output.

## Phase 5 - Frontend Registry And Type Migration

- [x] `P5.1` Add frontend split registry for the 4 canonical modes.
- [x] `P5.2` Replace hardcoded split menu items in `GraphNode`.
- [x] `P5.3` Replace hardcoded split mode wiring in `TreeGraph`.
- [x] `P5.4` Replace hardcoded split mode wiring in `GraphWorkspace`.
- [x] `P5.5` Replace store literals in `frontend/src/stores/project-store.ts`.
- [x] `P5.6` Replace API client literals in `frontend/src/api/client.ts`.
- [x] `P5.7` Migrate `NodeRecord.planning_mode` to the new canonical set.
- [x] `P5.8` Migrate `PlanningEvent.mode` to the new canonical set.
- [x] `P5.9` Migrate `SplitAcceptedResponse.mode` to the new canonical set.

## Phase 6 - Split Surface Cleanup

- [ ] `P6.1` Assert GraphNode as the sole split entrypoint.
- [ ] `P6.2` Remove or hide stale, duplicated, or placeholder split affordances outside GraphNode.
- [ ] `P6.3` Confirm no non-GraphNode UI path can initiate a canonical-mode split.
- [ ] `P6.4` Update stale docs that still point to `GraphControls` or `routes/nodes.py`.

## Phase 7 - Cutover Cleanup And Convergence

- [ ] `P7.1` Remove old split mode assumptions from persisted primary-path types and readers.
- [ ] `P7.2` Remove old split mode assumptions from planning history surfaces.
- [ ] `P7.3` Remove old split mode assumptions from replay surfaces.
- [ ] `P7.4` Record any unavoidable migration risk in `OPEN_ISSUES.md` instead of reintroducing ad hoc legacy behavior.

## Phase 8 - Tests And Docs

- [ ] `P8.1` Add prompt builder tests for all 4 canonical modes.
- [ ] `P8.2` Add parser and validator tests for strict flat-schema acceptance.
- [ ] `P8.3` Add service tests for `flat_subtasks_v1` materialization.
- [ ] `P8.4` Add service tests for the Phase 3 invariant.
- [x] `P8.5` Add deterministic fallback tests for each mode's semantics and count limits.
- [x] `P8.6` Add API tests for accepted modes and invalid mode returning `400 invalid_request`.
- [x] `P8.7` Add frontend tests for dynamic GraphNode split menu rendering.
- [x] `P8.8` Add frontend tests for removal or hiding of duplicate split affordances elsewhere.
- [ ] `P8.9` Add replace and supersede lifecycle tests:
- [ ] `P8.9.a` replace confirm flow
- [ ] `P8.9.b` superseding prior children
- [ ] `P8.9.c` parent `planning_mode`
- [ ] `P8.9.d` stable `split_metadata`
- [ ] `P8.9.e` replay or history after replace
