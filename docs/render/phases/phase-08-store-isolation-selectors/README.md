# Phase 08 - Store Isolation and Selectors

Status: Planned.

Scope IDs: C05, C06, C08.

Subphase workspace: ./subphases/.


## Objective

Reduce invalidation fanout by separating store concerns, tightening selectors, and narrowing forced reload behavior.

## In Scope

1. C05: Split store concerns.
2. C06: Narrow selectors.
3. C08: Smarter fallback reload policy.

## Detailed Improvements

### 1. Store concern separation (C05)

Split data domains:

- conversation/core thread state
- transport/connection state
- UI control/interaction state

This prevents unrelated updates from invalidating message-heavy views.

### 2. Selector narrowing (C06)

Ensure components subscribe only to required fields:

- row components: one item by ID + minimal flags
- status components: transport/lifecycle only
- avoid broad root selectors

### 3. Reload policy hardening (C08)

Force full reload only for true corruption/mismatch cases:

- explicit replay gap mismatch
- unrecoverable schema mismatch
- invalid order invariant breach

## Implementation Plan

1. Introduce clear store modules with stable interfaces.
2. Replace broad selectors with targeted memoized selectors.
3. Add reload-reason enum and centralized decision function.

## Quality Gates

1. Fanout:
   - reduced component invalidation per event.
2. Stability:
   - fewer unnecessary full reloads.
3. Debuggability:
   - every forced reload has explicit reason code.

## Test Plan

1. Unit tests:
   - selector dependency isolation.
   - reload decision logic matrix.
2. Integration tests:
   - event stream with transient reconnect issues should avoid unnecessary reload.
3. Manual checks:
   - inspect rerender behavior in active thread.

## Risks and Mitigations

1. Risk: selector bugs show stale UI fragments.
   - Mitigation: strict tests for critical selectors and row updates.
2. Risk: under-triggered reload causes divergence.
   - Mitigation: keep explicit invariant checks and safe fallback path.

## Handoff to Phase 09

With store invalidation reduced, row-level memoization and render cache can deliver clearer gains.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-6 engineering days
- Suggested staffing: 1 frontend primary + 1 QA support
- Confidence level: Medium (depends on current code-path complexity and test debt)



