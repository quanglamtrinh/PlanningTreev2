# Phase 10 - Progressive and Virtualized Rendering

Status: Planned (preflight frozen).

Date: 2026-04-13.

Scope IDs: D03, D04, D09.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Improves large-thread UX after state-level correctness and isolation are in place.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Virtualization must preserve anchor/load-more invariants.
- Progressive rendering must not break deterministic ordering.
- Budget degradation logic must preserve correctness before aesthetics.

## Objective

Keep long-thread interaction smooth by limiting mount pressure and controlling frame-time budget.

Frozen preflight artifacts:

1. `preflight-v1.md`
2. `list-anchor-invariants-v1.md` (`list_anchor_invariants_frozen`)

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

## Preflight-locked Defaults

1. Virtualization unit v1 is `groupedEntries` (no row flattening in first implementation pass).
2. Anchor policy v1 preserves viewport anchor for prepend/load-more.
3. Auto-scroll pinning remains allowed only when viewport is already near bottom.
4. Correctness fallback is mandatory: if anchor invariant breaks, degrade to safe non-virtualized mode.
5. No `C1`-`C6` contract expansion is allowed in preflight.

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

Gate harness:

1. `scripts/phase10_long_thread_open_scenario.py`
2. `scripts/phase10_scroll_smoothness_profile.py`
3. `scripts/phase10_virtualization_anchor_tests.py`
4. `scripts/phase10_gate_report.py`

Evidence contract:

- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/README.md`

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
