# Phase 13 Queue Confirmation Risk Policy v1

Status: Frozen policy artifact.

Phase: `phase-13-queued-follow-up-flow`.

Contract alignment:

1. Primary: `C6` Queue Contract v1.
2. Secondary: `C3` Lifecycle and Gating Contract v1.

## 1. Scope

This policy applies only to the `execution` lane in Phase 13.

Out of scope for this phase:

1. `ask_planning` queue behavior changes.
2. backend wire/schema changes.
3. observability and rollout/safety layers (deferred by phase planning).

## 2. Frozen Thresholds

1. `AUTO_SEND_MAX_AGE_MS = 90_000`
2. `QUEUE_MAX_ITEMS = 20`

Threshold interpretation:

1. An item older than `AUTO_SEND_MAX_AGE_MS` is stale and must be confirmed before send.
2. Queue length is bounded to `QUEUE_MAX_ITEMS` (new enqueue keeps latest bounded set).

## 3. Send Window Definition

A queued execution follow-up is eligible for automatic send only when all are true:

1. `workflowState.canSendExecutionMessage === true`
2. `workflowState.workflowPhase === "execution_decision_pending"`
3. `snapshot.activeTurnId == null`
4. `snapshot.processingState === "idle"`
5. no pending user-input request with status `requested` or `answer_submitted`
6. operator pause is not enabled
7. plan-ready gate is not active

Plan-ready gate active condition:

1. `planReady.ready === true`
2. `planReady.failed === false`
3. `planReady.planItemId` is non-empty
4. `planReady.revision != null`

## 4. Risk Triggers Requiring Confirmation

An entry transitions to `requires_confirmation` before send when any trigger is true:

1. Age trigger:
   - `Date.now() - entry.createdAtMs > AUTO_SEND_MAX_AGE_MS`
2. Execution-run context trigger:
   - `enqueueContext.latestExecutionRunId` differs from current `latestExecutionRunId`
   - only when both values are non-empty
3. Plan-ready revision context trigger:
   - `enqueueContext.planReadyRevision` differs from current `planReady.revision`
   - trigger applies when either side is non-null

Safety invariant:

1. `requires_confirmation` items are never auto-sent.
2. Manual `Send now` still enforces this confirmation policy.
3. Only explicit `Confirm` can re-qualify stale/risky items for send.

## 5. Operator Controls

1. `Pause auto-send` blocks automatic flush but preserves queue.
2. `Send now` is permitted during plan-ready gate and uses the same risk checks.
3. `Confirm` re-stamps context for stale/risky item and then allows send attempt.
4. Queue mutations (`remove`, `reorder`, `retry`, `confirm`) are blocked while an item is in `sending`.

## 6. Evidence Requirements

This policy is considered validated when all phase gate sources pass:

1. `queue_state_machine_suite` (`P13-G1`)
2. `queue_reorder_integration` (`P13-G2`)
3. `queue_risk_policy_tests` (`P13-G3`)

Hard requirement for `P13-G3`:

1. `stale_intent_unconfirmed_send_events` must be `0`.
