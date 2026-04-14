# Phase A7 - Test Matrix and Controlled Enablement

Status: Planned.

Phase ID: `AQ7`.

## Objective

Finalize ask queue migration with a complete test matrix and controlled rollout/enablement strategy.

## In Scope

1. Build ask queue acceptance matrix:
   - unit
   - integration
   - UI/e2e critical scenarios
2. Add ask queue feature gate:
   - `ask_followup_queue_enabled` (frontend/backend coordinated behavior)
3. Controlled enablement stages:
   - internal
   - canary
   - broad rollout
4. Define rollback path:
   - disable ask queue gate and return ask tab to direct-send behavior

## Out of Scope

1. New core queue features.
2. Execution workflow behavior changes.

## Acceptance Matrix (minimum)

1. Functional:
   - ask enqueue, auto-flush, confirmation, retry, remove, reorder.
2. Reliability:
   - reconnect, reload, reset, retry-no-duplicate.
3. Compatibility:
   - execution queue parity suite unchanged.
4. Safety:
   - ask read-only policy still enforced end-to-end.

## Implementation Plan

1. Test suites:
   - add/expand lane-aware queue tests in `threadByIdStoreV3`.
   - add `BreadcrumbChatViewV2` ask queue integration tests.
2. Rollout controls:
   - gate guard in ask send path.
   - gate status surfaced for debugging.
3. Rollback readiness:
   - documented rollback checklist and smoke test.

## Quality Gates

1. Test gate:
   - agreed acceptance matrix is fully green.
2. Rollout gate:
   - internal and canary windows pass without blocker regressions.
3. Rollback gate:
   - rollback procedure validated at least once in staging.

## Test Plan

1. Unit:
   - lane-aware queue state transitions and policy checks.
2. Integration:
   - ask tab queue flows across lifecycle/reconnect/reset paths.
3. Targeted e2e:
   - critical ask user journey with queued follow-ups.
4. Regression:
   - existing execution queue suites remain green.

## Risks and Mitigations

1. Risk: hidden production-only race conditions.
   - Mitigation: canary with detailed event logging around queue transitions.
2. Risk: rollback misses persisted queue edge.
   - Mitigation: include persistence compatibility checks in rollback smoke.

## Exit Criteria

1. Ask queue migration is production-ready behind controlled gate.
2. Team has validated rollback and regression posture.

## Effort Estimate

- Size: Medium
- Estimated duration: 3-5 engineering days
- Suggested staffing: 1 frontend + 1 backend + QA support

