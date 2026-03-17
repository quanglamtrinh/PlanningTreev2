# Phase 6.3 Plan: Compatibility Cleanup And Gate-Based Removal

## Inheritance
- This subphase inherits all Phase 6 entry conditions, invariants, gate rules, and cleanup boundaries from `PHASE_6_PLAN.md`.
- It narrows Phase 6 to compatibility inventory, classification, and gate-qualified removal only.

## Summary
- Phase 6.3 removes transitional compatibility behavior only after the replacement path is already validated.
- Every target must be inventoried, classified, and logged before cleanup can start.

## Source Context Anchors
- `docs/codebase-map.md`
- `docs/app-server-events.md`
- `src/services/events.ts`
- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/threads/hooks/useThreads.ts`
- `src/features/threads/hooks/useThreadActions.ts`
- `src/services/tauri.ts`

## Scope
- legacy adapters
- duplicate routing
- shadow state
- redundant reconnect paths
- temporary migration compatibility layers

## Batch Defaults
- `P6.3.a` compatibility inventory and classification
- `P6.3.b` gate-qualified bounded removals
- `P6.3.c` post-removal verification and permanent architecture record

## Acceptance Criteria
- every cleanup target is classified before removal
- every removal names its replacement path and rollback impact
- every removal references exact enabling gate evidence
- no blocked or uncertain target is removed
- docs distinguish permanent architecture from removed transitional code

## Assumptions
- cleanup is bounded and gate-based
- cleanup is not allowed to force adoption of an unstable replacement path
