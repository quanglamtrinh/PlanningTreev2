# Phase 13 - Queued Follow-up Flow

Status: Planned.

Scope IDs: E04, E05, E06.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Implements CodexMonitor-style queue UX under strict lifecycle and safety contracts.

Contract focus:

- Primary: `C6 Queue Contract v1`
- Secondary: `C3 Lifecycle and Gating Contract v1`

Must-hold decisions:

- Queue state machine is deterministic and lifecycle-driven.
- Confirmation policy is risk-based (not always-confirm, not always-auto-send).
- Queue controls must preserve message order guarantees.


## Objective

Make follow-up sending reliable and user-controllable while a turn is still processing or gated.

## In Scope

1. E04: Queue follow-up messages while processing.
2. E05: Queue pause on gated states.
3. E06: Queue UX controls.

## Detailed Improvements

### 1. Follow-up queue baseline (E04)

When an active turn is running:

- enqueue additional user messages
- do not fail or race-send immediately
- flush queue when send window opens

### 2. Gated-state pause/resume (E05)

Queue must pause in states where auto-send is unsafe:

- waiting for user input/approval
- plan-ready gated state
- explicit operator pause

Resume rules must be explicit and deterministic.

### 3. Queue UX controls (E06)

Add user controls:

- reorder queued items
- remove queued item
- send selected item now (when allowed)

## Implementation Plan

1. Introduce queue state machine with explicit transitions.
2. Connect lifecycle states to queue pause/resume policy.
3. Build queue panel interactions and keyboard-safe controls.
4. Add clear status text so users understand queued vs active behavior.

## Quality Gates

1. Reliability:
   - no lost follow-up messages during active turns.
2. Correctness:
   - queue ordering and pause/resume behavior match policy.
3. UX:
   - users can inspect and control queued intents clearly.

## Test Plan

1. Unit tests:
   - queue state machine transitions and edge cases.
2. Integration tests:
   - submit multiple follow-ups during active processing and gated states.
3. Manual checks:
   - reorder/remove/send-now behavior with real stream activity.

## Risks and Mitigations

1. Risk: queue sends stale intent after context changes.
   - Mitigation: require visible queue review and optional confirmation on long delays.
2. Risk: policy confusion across gated states.
   - Mitigation: single authoritative gating matrix and UI status mapping.

## Completion Criteria

Phase 13 closes when:

1. Follow-up queue behavior is deterministic in active and gated flows.
2. Manual stress tests show no race-send regressions.
3. Queue UX controls are stable for both mouse and keyboard interactions.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-6 engineering days
- Suggested staffing: 1 frontend primary + 1 backend support
- Confidence level: Medium (depends on current code-path complexity and test debt)




