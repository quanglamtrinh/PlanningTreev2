# Phase 12 - Data Volume and Heavy Content UX

Status: Planned.

Scope IDs: D08, E01, E02, E03.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Applies data-volume governance after backend canonical event shaping and render hardening.

Contract focus:

- Primary: `C5` Frontend State Contract v1
- Secondary: `C4` Durability Contract v1

Must-hold decisions:

- Semantic text coalescing remains backend-owned and canonical.
- Frontend truncation/collapse is a view policy, not data mutation.
- Archived/load-more flow must preserve ordering and recoverability.


## Objective

Control active data volume and heavy content defaults so performance remains stable as threads grow.

## In Scope

1. D08: Default-collapse heavy rows.
2. E01: Conversation scrollback cap.
3. E02: Large payload truncation policy.
4. E03: Coalesce consecutive assistant text chunks pre-storage.

## Detailed Improvements

### 1. Default collapsed heavy rows (D08)

Auto-collapse rows above configured complexity/size thresholds:

- large diff rows
- huge tool payload rows
- large command output rows

User can expand on demand.

### 2. Active scrollback cap (E01)

Keep in-memory live item window bounded (e.g. 500/1000/2000 configurable):

- older rows move to archived segment
- provide load-more mechanism

### 3. Payload truncation UX (E02)

For very large payloads:

- show preview excerpt in primary render path
- provide link/action to open full artifact view

### 4. Assistant chunk coalescing (E03)

Merge adjacent assistant text chunks before storage/render, reducing row count and downstream rendering work.

## Implementation Plan

1. Add heavy-row classification utility and default collapsed UI behavior.
2. Implement scrollback window management in state/store pipeline.
3. Add truncation formatter with explicit "view full" affordance.
4. Coalesce adjacent text blocks in backend pipeline as canonical source of truth; frontend remains presentation-only.

## Quality Gates

1. Data volume control:
   - bounded memory growth for long-running threads.
2. UX clarity:
   - users can still access full content intentionally.
3. Performance:
   - improved initial open and update cost on large threads.

## Test Plan

1. Unit tests:
   - heavy-row classification thresholds.
   - chunk coalescing correctness.
2. Integration tests:
   - very long thread with repeated large payload events.
3. Manual checks:
   - expand/collapse and full-artifact navigation behavior.

## Risks and Mitigations

1. Risk: hidden important content due to over-aggressive collapse/truncation.
   - Mitigation: conservative defaults and explicit expand indicators.
2. Risk: context loss from scrollback cap.
   - Mitigation: reliable load-more path with preserved ordering.

## Handoff to Phase 13

With content volume stabilized, queue behavior improvements can focus on active-turn UX and reliability.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-6 engineering days
- Suggested staffing: 1 frontend + 1 backend (shared)
- Confidence level: Medium (depends on current code-path complexity and test debt)





