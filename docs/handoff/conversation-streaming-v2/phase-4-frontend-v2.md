# Phase 4: Frontend V2 Reducer and Renderer

Status: not started.

## Goal

Build the frontend V2 conversation path around canonical items, patch semantics, direct render-by-kind, and shared hydration plus live event state.

## In Scope

- API typing for V2 payloads
- V2 reducer, store, and event router
- V2 workflow event bridge
- V2 conversation rendering components
- reconnect and hydration behavior

## Out of Scope

- production cutover for all users
- deletion of V1 frontend files
- non-conversation detail-state redesign

## File Targets

- `frontend/src/api/types.ts`
- frontend API client for thread V2 routes
- `frontend/src/features/conversation/state/threadStoreV2.ts`
- `frontend/src/features/conversation/state/applyThreadEvent.ts`
- `frontend/src/features/conversation/state/threadEventRouter.ts`
- `frontend/src/features/conversation/state/workflowEventBridge.ts`
- `frontend/src/features/conversation/components/*`

## Checklist

- define frontend types that mirror the active spec exactly
- implement reducer logic for snapshot, upsert, patch, lifecycle, reset, and error events
- reject patch events for missing items through mismatch handling
- implement renderers for `message`, `reasoning`, `plan`, `tool`, `userInput`, `status`, and `error`
- derive working indicator from lifecycle state instead of semantic block heuristics
- keep workflow state in side-channel logic, not conversation reducer
- verify `outputFilesReplace` overwrites preview file lists
- keep V1 client path isolated during mixed-mode rollout

## Verification

- reducer unit tests
- view-state tests
- fixture-driven rendering tests
- reconnect and reload integration tests against sandbox V2 endpoints

## Exit Criteria

- frontend V2 path renders only from canonical items
- no pair-based reducer logic exists in V2
- semantic mapper is not needed for the V2 path

## Artifacts To Produce

- `artifacts/phase-4/reducer-fixture-matrix.md`
- `artifacts/phase-4/rendering-screenshots.md`
- `artifacts/phase-4/reconnect-notes.md`
