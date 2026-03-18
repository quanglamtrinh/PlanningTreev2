# Phase 1 Plan: Split Registry And Route Guard

Last updated: 2026-03-17

## Phase Goal

- Add a canonical split contract scaffold and close the `/split` route boundary without breaking the current GraphNode-driven split runtime.
- Land a temporary route bridge for `walking_skeleton` and `slice` as an implementation bridge only, not as a reversal of the final hard-cutover policy.

## In-Scope Changes

- Add `backend/split_contract.py` with the canonical mode registry and route parser.
- Convert `backend/routes/split.py` from open string forwarding to explicit route parsing and guarding.
- Preserve `400 invalid_request` for unknown modes.
- Guard canonical new modes at the route with a fixed `409 split_not_allowed` message until later phases land.
- Keep temporary acceptance of `walking_skeleton` and `slice` so the current runtime remains usable.
- Add unit and integration coverage for the new contract and route behavior.

## Out-Of-Scope Boundaries

- Prompt builder refactor.
- Shared flat-schema parser or validator.
- `SplitService` output-family refactor.
- Deterministic fallback migration.
- Frontend registry or UI exposure changes.
- Final removal of the temporary legacy route bridge.

## Implementation Tasks

- Add `CanonicalSplitModeId`, `SplitOutputFamily`, `SplitModeSpec`, `CANONICAL_SPLIT_MODE_REGISTRY`, `TEMPORARY_LEGACY_ROUTE_BRIDGE`, and `parse_route_split_mode_or_raise(...)`.
- Keep `SplitNodeRequest.mode` as `str` and parse it manually inside the route to avoid default framework validation behavior changing bad-mode status codes.
- Forward legacy bridge modes to the current `SplitService` path unchanged.
- Reject canonical new modes before the service is called.
- Add tests proving:
  - registry contents and metadata are correct
  - parser accepts canonical and bridge modes
  - bad modes still return `400 invalid_request`
  - canonical modes are guarded with `409 split_not_allowed`
  - route guard triggers before `split_service.split_node(...)`

## Acceptance Checks

- Unknown split mode returns `400 invalid_request`.
- `walking_skeleton` and `slice` still execute through the current path.
- `workflow`, `simplify_workflow`, `phase_breakdown`, and `agent_breakdown` are recognized but not executable yet.
- The route is no longer an open arbitrary-string contract.

## Open Phase-Local Risks

- The temporary route bridge must be removed in later cutover phases and must not silently become permanent policy.
- `SplitNodeRequest.mode` remains a `str` field, so non-string request-body shape issues are still owned by Pydantic rather than the custom route parser.
