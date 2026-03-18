# Phase 5 Progress

Last updated: 2026-03-17

## Entries

### 2026-03-17

- Started and completed Phase 5 by opening the public `/split` route for the 4 canonical modes and removing legacy modes from the public split contract.
- Added frontend canonical split typing and a graph split registry so GraphNode now renders canonical split actions dynamically.
- Rewired `TreeGraph`, `GraphWorkspace`, `project-store`, and the API client to use canonical `SplitMode` create paths only.
- Removed split buttons from `PlanningConversationPanel`, leaving GraphNode as the only exposed split entrypoint.
- Added shared split-payload normalization so canonical flat subtasks render correctly while legacy split payloads remain readable on transition read paths.
- Extended backend and frontend test coverage for canonical route acceptance, canonical graph/store wiring, duplicate split affordance removal, and canonical split-result rendering.

## Notable Changes Landed

- Public canonical route flip in `backend/routes/split.py` and canonical-only route parsing in `backend/split_contract.py`.
- Frontend `SplitMode` registry in `frontend/src/features/graph/splitModes.ts`.
- Canonical split menu rendering in `GraphNode`, generic `onSplit(nodeId, mode)` wiring in `TreeGraph`, and canonical mode handling in `GraphWorkspace`.
- Shared split payload normalizer in `frontend/src/features/conversation/model/normalizeSplitPayload.ts`.
- Canonical flat split-result rendering support in both conversation surfaces while keeping legacy read compatibility.

## Blockers Or Scope Changes

- None.

## Remaining Work

- Phase 6 split-surface cleanup for stale placeholders such as GraphControls.
- Phase 7 cutover cleanup for remaining legacy assumptions in primary-path readers.
- Phase 8 final test and docs stabilization.
