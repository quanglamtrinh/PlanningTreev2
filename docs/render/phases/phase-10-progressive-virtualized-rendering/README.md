# Phase 10 - Progressive and Virtualized Rendering

Status: Planned.

Scope IDs: D03, D04, D09.

Subphase workspace: ./subphases/.


## Objective

Keep long-thread interaction smooth by limiting mount pressure and controlling frame-time budget.

## In Scope

1. D03: Progressive rendering for long history.
2. D04: Virtualization for very long feeds.
3. D09: Render budget guard.

## Detailed Improvements

### 1. Progressive row mount (D03)

On large thread open:

- mount initial visible chunk first
- mount remaining rows in controlled batches
- prioritize keeping input/scroll responsive

### 2. Viewport virtualization (D04)

Render only visible rows + overscan:

- reduce DOM node count
- reduce layout/paint cost
- maintain anchor correctness on prepend/load-more

### 3. Render budget guard (D09)

When frame cost exceeds budget:

- reduce per-frame mount batch size
- defer non-critical decoration work
- keep interaction path responsive

## Implementation Plan

1. Integrate progressive list behavior into message feed.
2. Add virtualization layer with stable key and dynamic height strategy.
3. Add runtime budget monitor for adaptive degrade behavior.

## Quality Gates

1. Long-thread open:
   - improved time-to-interactive for large threads.
2. Scroll quality:
   - stable scroll with low jank under long histories.
3. Budget control:
   - guard activates only under stress and preserves correctness.

## Test Plan

1. Component tests:
   - anchor stability while loading additional history.
2. Integration tests:
   - open large thread scenarios with mixed content rows.
3. Manual checks:
   - scroll smoothness and input responsiveness.

## Risks and Mitigations

1. Risk: virtualization breaks sticky behaviors or anchors.
   - Mitigation: explicit anchor tests and fallback mode.
2. Risk: adaptive guard causes visible content delay.
   - Mitigation: cap degrade level and preserve critical content priority.

## Handoff to Phase 11

With base list performance under control, heavy compute offload can focus on specific expensive row types.


## Effort Estimate

- Size: Large
- Estimated duration: 6-8 engineering days
- Suggested staffing: 1 frontend primary + 1 frontend support
- Confidence level: Medium (depends on current code-path complexity and test debt)



