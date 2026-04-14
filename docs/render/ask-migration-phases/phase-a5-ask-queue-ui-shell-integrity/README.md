# Phase A5 - Ask Queue UI Parity and Shell Integrity

Status: Planned.

Phase ID: `AQ5`.

## Objective

Expose ask queue controls in UI with execution-level usability, while preserving ask metadata shell behavior and layout contracts.

## In Scope

1. Add ask queue panel in ask tab:
   - queue list
   - status badge
   - move up/down
   - remove
   - send now
   - confirm
   - retry
2. Update ask composer disabled logic to align queue-first semantics.
3. Preserve `FrameContextFeedBlock` rendering and action-chip behavior.
4. Keep execution queue UI intact.

## Out of Scope

1. Recovery edge-case hardening (A6).
2. Rollout strategy and flags (A7).

## UX Constraints

1. Ask queue controls must not break current metadata shell context visibility.
2. Queue status labels must clearly explain paused/confirmation states.
3. Ask shell action-state chips remain independent from queue rendering.

## Implementation Plan

1. Extend `BreadcrumbChatViewV2` ask branch:
   - render queue panel for ask lane
   - wire actions to lane-aware queue core
2. Add ask-specific pause reason labels.
3. Validate layout for desktop and mobile widths.

## Quality Gates

1. UX integrity:
   - ask context shell is still visible and stable.
2. Queue usability:
   - user can inspect and control queued ask entries clearly.
3. Non-regression:
   - execution panel behavior and controls unchanged.

## Test Plan

1. Unit/component tests:
   - ask tab queue panel render and control actions.
2. Integration tests:
   - ask queue actions with active turn transitions.
3. Visual/manual checks:
   - metadata shell + queue panel coexistence on ask tab.

## Risks and Mitigations

1. Risk: UI crowding in ask tab.
   - Mitigation: progressive disclosure and compact list styling.
2. Risk: confusion between shaping actions and queue actions.
   - Mitigation: separate visual grouping and explicit labels.

## Exit Criteria

1. Ask queue controls are fully usable in ask tab.
2. Ask shell behavior remains intact and regression-safe.

## Effort Estimate

- Size: Medium
- Estimated duration: 3-5 engineering days
- Suggested staffing: 1 frontend primary + 1 design reviewer

