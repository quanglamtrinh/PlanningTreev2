# Phase A7 - Test Matrix and Controlled Enablement

Status: In progress.

Phase ID: `AQ7`.

## Objective

Unblock AQ7 closure with rollout-safe ask queue control and complete gate evidence automation.

## Mandatory Deliverables

1. Ask rollout gate wiring (`ask_followup_queue_enabled`) with default-off behavior.
2. AQ7 source evidence automation:
   - `ask_queue_acceptance_matrix.json`
   - `ask_canary_stability_report.json`
   - `ask_rollback_drill_report.json`
3. AQ7 gate aggregation:
   - `phase-a7-gate-report.json`
4. Standardized test and rollback runbook for closeout.

## Scope Boundaries

1. In scope:
   - ask lane rollout control plane
   - ask lane queue panel gating
   - ask lane queue hydration/flush disable path when gate is off
   - AQ7 evidence scripts and closeout docs
2. Out of scope:
   - new ask queue features
   - execution lane behavior changes
   - audit lane behavior changes

## Gate Semantics

1. Gate default is off: `PLANNINGTREE_ASK_FOLLOWUP_QUEUE_ENABLED=false`.
2. Gate off behavior:
   - ask direct-send path via `startThreadTurnRequest`
   - no ask queue panel render
   - no ask queue hydration from local storage
   - no ask auto-flush
   - clear stale ask queue storage for current thread key
3. Gate on behavior:
   - queue-first ask flow remains active
   - existing ask queue actions (retry/reorder/remove/confirm/send-now) remain active

## Gate Thresholds (AQ7)

1. `AQ7-G1`: `ask_queue_acceptance_suite_pass_rate_pct >= 100`
2. `AQ7-G2`: `ask_canary_blocker_incidents <= 0`
3. `AQ7-G3`: `ask_rollback_drill_failures <= 0`

## Evidence Eligibility Policy

1. Only `evidence_mode=candidate` with `gate_eligible=true` is valid for closure.
2. `evidence_mode=synthetic` with `gate_eligible=false` is local dry-run only.

## Standard Closeout Command Order

1. `npm run check:freeze_all`
2. `npm run typecheck --prefix frontend`
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts BreadcrumbChatViewV2.test.tsx`
4. `python -m pytest backend/tests/unit/test_ask_v3_rollout_phase6_7.py`
5. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "ask_reset_by_id_clears_thread_snapshot or ask_reset_by_id_publishes_workflow_update or ask_idempotency_scope_does_not_cross_reset_to_new_thread"`
6. `npm run check:ask_phase_a7_evidence`

## Rollout Path

1. internal
2. canary
3. broad

Rollback is always gate-off first (`ask_followup_queue_enabled=false`) before deeper triage.
