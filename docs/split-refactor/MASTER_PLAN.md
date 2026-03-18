# Master Plan: Split Refactor

Last updated: 2026-03-17

## Purpose

- Create a single authoritative scaffold for the split refactor effort.
- Drive the work backend-first, then wire the UI to the final contract.
- Replace the old split contract with a new canonical contract built around 4 supported modes and 1 shared output family.
- Keep this artifact set decision-complete enough that later phase docs can inherit from it without reopening core contract questions.

## Summary

- Maintain exactly this artifact structure under `docs/split-refactor/`.
- Do not pre-create empty phase docs.
- Treat this effort as a hard cutover to the new split contract.
- Lock the GraphNode menu as the sole split entrypoint after cleanup.

## Current-State Evidence

The following facts were re-checked while creating this scaffold on 2026-03-17:

- `frontend/src/features/graph/GraphNode.tsx` is a live split surface.
- A legacy graph-side action panel still existed only as placeholder split affordances before Phase 6 cleanup.
- `backend/routes/split.py` still accepts `mode` at the split route boundary as an open string contract and must be converted to a closed supported-mode contract without drifting to framework-default invalid-mode behavior.
- `backend/services/split_service.py` currently branches directly on mode strings and must be refactored away from mode-specific branching.
- `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, and `frontend/src/stores/project-store.ts` still encode old planning mode literals and must be replaced with the new canonical set.
- Some current docs still described outdated split UI ownership and route ownership before the cleanup phases landed.
- No additional live split surface is asserted in this plan unless it is re-verified when implementation starts.

## Canonical Mode Matrix

| id | visible_in_ui | accepted_at_route | output_family | creation_enabled |
| --- | --- | --- | --- | --- |
| `workflow` | true | true | `flat_subtasks_v1` | true |
| `simplify_workflow` | true | true | `flat_subtasks_v1` | true |
| `phase_breakdown` | true | true | `flat_subtasks_v1` | true |
| `agent_breakdown` | true | true | `flat_subtasks_v1` | true |

## Mode Contract

### Hard Contract Rules

- `walking_skeleton` and `slice` are removed from the supported mode set.
- `phase_breakdown` must not map to `walking_skeleton`.
- All 4 canonical modes share the same output family: `flat_subtasks_v1`.
- The shared flat schema is fixed to:

```text
subtasks[
  {
    id,
    title,
    objective,
    why_now
  }
]
```

- No extra keys are allowed for new modes.

### New-Mode Contract

| mode | min_items | max_items | output_family |
| --- | --- | --- | --- |
| `workflow` | 3 | 7 | `flat_subtasks_v1` |
| `simplify_workflow` | 2 | 5 | `flat_subtasks_v1` |
| `phase_breakdown` | 3 | 6 | `flat_subtasks_v1` |
| `agent_breakdown` | 4 | 7 | `flat_subtasks_v1` |

### Mode Semantics

- `workflow`: workflow-first sequential split.
- `simplify_workflow`: minimum valid core workflow first, then additive reintroduction.
- `phase_breakdown`: phase-based sequential delivery split.
- `agent_breakdown`: conservative non-workflow split when the other shapes are a weak fit.

## Compatibility And Cutover Policy

This effort is a contract replacement, not a dual-mode compatibility campaign.

### Locked Policy

- Only the 4 canonical modes are supported after cutover.
- Old `walking_skeleton` and `slice` are not valid new-creation paths.
- Backend route no longer accepts old modes after cutover.
- Old legacy split compatibility is out of scope unless implementation reveals an unavoidable migration need.
- No schema bump is planned initially.
- If existing persisted data proves incompatible, the only allowed escalation is an explicit cutover or migration plan added later. Do not silently reintroduce legacy mode support.

### Reader Expectations

- Do not promise old split replay or readability by default.
- Treat existing old-mode data as migration-risk surface, not as guaranteed compatibility.
- If cutover spikes reveal unavoidable old-data breakage that matters, capture it in `OPEN_ISSUES.md` and resolve it explicitly.

## split_metadata Policy

### Stable Fields

Stable fields must include:

- `mode`
- `output_family`
- `source`
- `warnings`
- `created_child_ids`
- `replaced_child_ids`
- `created_at`
- `revision`

### Stable Materialization Record

New flat-family splits must persist a stable normalized materialization record that replay and UI can depend on. At minimum preserve:

- normalized child order
- normalized subtask title
- normalized objective
- normalized `why_now`
- parent-to-created-child mapping

### Debug Payload

- Raw generation or debug payload may be stored under a clearly debug-scoped key.
- UI and replay must not depend on raw debug payload shape.

### Field Meaning Guidance

- `source`: stable producer identity such as model or fallback.
- `warnings`: normalized user-safe warnings, not arbitrary parser noise.
- `revision`: materialization contract revision for this metadata shape, not a whole-system schema version.

## Phased Rollout

### Phase 1

Add canonical split registry and route-facing supported-mode adapter or parser, while preserving explicit `400 invalid_request` behavior for bad modes instead of drifting to FastAPI default `422`.

### Phase 2

Refactor `backend/ai/split_prompt_builder.py` to registry-driven builders with:

- shared flat-schema example
- shared parser
- shared validator
- shared hidden-retry contract

Remove legacy-mode parsing paths from the main split contract.

### Phase 3

Refactor `SplitService` to branch by `output_family`, not by mode string.

Phase 3 invariant:

- new-mode materialization must depend only on `output_family` and the shared flat-subtask contract
- never on mode-specific payload keys

Phase 3 flat-family behavior:

- one child per subtask
- child title from `title`
- child description from `objective + why_now`
- stable materialization metadata recorded
- raw item optionally recorded under a debug-scoped metadata key

### Phase 4

Replace deterministic fallback for all 4 modes with flat-schema outputs and mode-specific semantics.

Fallback must become a first-class producer of the same `flat_subtasks_v1` contract used by model output.

### Phase 5

Add frontend split registry and replace hardcoded literals in:

- `GraphNode`
- `TreeGraph`
- `GraphWorkspace`
- store
- API client
- transport and types

Expose only the 4 canonical modes in the GraphNode menu.

### Phase 6

Assert GraphNode menu as the sole split entrypoint and remove or keep hidden any stale, duplicated, or placeholder split affordances elsewhere. Update stale docs accordingly.

Phase 6 close condition:

- no non-GraphNode UI path can initiate a new split for canonical modes

### Phase 7

Complete cutover handling for persisted `planning_mode`, planning events, history surfaces, and replay surfaces so the repo no longer assumes or exposes old split mode contracts anywhere in the primary path.

This is a cleanup-and-convergence phase, not a legacy-preservation phase.

### Phase 8

Finish tests and docs only after the technical contract is stable.

## Assumptions And Defaults

- Backend supports only the 4 canonical modes after cutover.
- `walking_skeleton` and `slice` are removed from the supported split contract.
- One shared `flat_subtasks_v1` output family serves all 4 modes.
- GraphNode is the sole split entrypoint after cleanup.
- No bulk phase-file generation is allowed.
- No legacy compatibility promise is made unless implementation later proves a migration path is required.

## Success Gates

This effort is complete only when:

- the supported split mode set contains exactly the 4 canonical modes
- route-level mode handling is closed over those 4 modes while preserving `400 invalid_request`
- prompt building, parsing, validation, service application, and fallback all converge on `flat_subtasks_v1`
- frontend exposure is registry-driven and limited to GraphNode
- no primary path still depends on old split mode literals
- stale docs are updated to match the final ownership and entrypoint model
