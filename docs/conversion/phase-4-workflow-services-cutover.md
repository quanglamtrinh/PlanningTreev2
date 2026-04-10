# Phase 4 - Workflow Services Cutover

Status: pending  
Estimate: 8-10 person-days (18%)

## 1. Objective

Move all workflow business paths to the V3 core:

- finish-task
- execution follow-up
- audit review
- rollup

There must be no V2 runtime/query coupling left in the production service-layer path.

## 2. In Scope

- `FinishTaskService`
- `ExecutionAuditWorkflowService`
- `ReviewService`
- Workflow event publisher integration for V3 state changes
- Do not write execution/audit transcripts to legacy `chat_state_store`

## 3. Out Of Scope

- Frontend control-plane migration
- Hard removal of V2 modules (handled in Phase 7)

## 4. Work Breakdown

- [ ] Refactor constructors/wiring to remove `_v2` naming from service state.
- [ ] Migrate call sites:
  - `begin_turn`, `stream_agent_turn`, `complete_turn`
  - `get_thread_snapshot`, `persist_thread_mutation`
  to V3 runtime/query services.
- [ ] Preserve behavior parity:
  - execution/audit does not emit legacy chat events
  - workflow invalidation reasons are complete
  - command/fileChange/reasoning semantics remain equivalent
- [ ] Keep `askThreadId` resolution policy (registry-first, bridge fallback only when needed).
- [ ] Update test doubles/fakes for service unit tests.

## 5. Deliverables

- Workflow services run natively on V3.
- Integration evidence:
  - the Phase 6 production cutover test still passes with the V3 core
- Artifacts:
  - `docs/conversion/artifacts/phase-4/service-call-graph-before-after.md`
  - `docs/conversion/artifacts/phase-4/behavior-parity-report.md`

## 6. Exit Criteria

- `FinishTaskService`, `ExecutionAuditWorkflowService`, and `ReviewService` no longer depend on V2 runtime/query services.
- Legacy `chat_state_store` transcripts for execution/audit are not mutated on the production path.
- Workflow state and mutation behavior does not drift from baseline.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
- [ ] `python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py`
- [ ] `python -m pytest -q backend/tests/unit/test_review_service.py`

## 8. Risks And Mitigations

- Risk: regression in long-running finish-task flows.
  - Mitigation: run production-like integration tests and add timeboxed watchdog assertions.
- Risk: drift in fileChange diff hydration.
  - Mitigation: run files-changed parity fixtures and hydration tests.
