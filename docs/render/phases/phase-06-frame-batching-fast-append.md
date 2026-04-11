# Phase 06 - Frame Batching and Fast Text Append

Status: Planned.

Scope IDs: C01, C07.

## Objective

Reduce frontend apply thrash by batching event application per animation frame and using a fast path for streaming text append.

## In Scope

1. C01: Frame-batched event apply (RAF batching).
2. C07: Fast-path text append.

## Detailed Improvements

### 1. RAF event queue (C01)

Instead of immediate apply per incoming event:

- enqueue events in a short-lived buffer
- flush on `requestAnimationFrame`
- process as one state transition batch

Result: burst events produce fewer store mutations and rerenders.

### 2. Fast append slot update (C07)

For streaming assistant text chunks:

- avoid generic patch walker
- use direct append path on known item slot
- skip expensive recomputation when only text tail changed

## Implementation Plan

1. Store layer:
   - add event queue and frame flush scheduler.
   - provide immediate flush on terminal/critical events.
2. Apply logic:
   - add text-append specialized path with strict guard conditions.
3. UI behavior:
   - ensure partial text remains responsive during batching.

## Quality Gates

1. Apply reduction:
   - burst event apply calls drop significantly.
2. Responsiveness:
   - no visible lag in live text stream.
3. Correctness:
   - final text content matches non-batched baseline.

## Test Plan

1. Unit tests:
   - RAF scheduler flush timing and ordering.
   - fast append guard conditions.
2. Integration tests:
   - high-frequency text streaming burst.
3. Manual checks:
   - compare visual smoothness before/after.

## Risks and Mitigations

1. Risk: delayed rendering from over-batching.
   - Mitigation: max queue age and forced flush policy.
2. Risk: fast path bypasses side-effects.
   - Mitigation: strict eligibility checks and fallback to generic path.

## Handoff to Phase 07

With apply frequency reduced, deeper state-shape optimizations can target remaining hot-path costs.

