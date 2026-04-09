# Phase 4 - Workflow Services Cutover

Status: pending  
Estimate: 8-10 person-days (18%)

## 1. Muc tieu

Chuyen toan bo workflow business path sang V3 core:

- finish-task
- execution follow-up
- audit review
- rollup

Khong con runtime/query coupling V2 o service layer production path.

## 2. In-scope

- `FinishTaskService`
- `ExecutionAuditWorkflowService`
- `ReviewService`
- Workflow event publisher integration voi V3 state changes
- Khong ghi transcript execution/audit vao legacy `chat_state_store`

## 3. Out-of-scope

- Frontend control-plane migration.
- Hard delete module V2 (se lam phase 7).

## 4. Work breakdown

- [ ] Refactor constructor/wiring bo ten `_v2` o service state.
- [ ] Chuyen call sites:
  - `begin_turn`, `stream_agent_turn`, `complete_turn`
  - `get_thread_snapshot`, `persist_thread_mutation`
  sang runtime/query V3.
- [ ] Dam bao behavior giu nguyen:
  - execution/audit khong phat legacy chat events
  - workflow invalidation reasons day du
  - command/fileChange/reasoning semantics giu parity
- [ ] Giu askThreadId resolution policy (registry-first, bridge fallback neu con can).
- [ ] Cap nhat test doubles/fakes cho service unit tests.

## 5. Deliverables

- Workflow services chay V3 native.
- Integration evidence:
  - phase6 production cutover test van pass voi V3 core.
- Artifacts:
  - `docs/conversion/artifacts/phase-4/service-call-graph-before-after.md`
  - `docs/conversion/artifacts/phase-4/behavior-parity-report.md`

## 6. Exit criteria

- `FinishTaskService`, `ExecutionAuditWorkflowService`, `ReviewService` khong con dependency runtime/query V2.
- Legacy chat_state transcript cho execution/audit khong bi mutate tren production path.
- Workflow state/mutation behavior khong drift.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
- [ ] `python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py`
- [ ] `python -m pytest -q backend/tests/unit/test_review_service.py`

## 8. Risks va giam thieu

- Risk: regression o finish-task long-running flow.
  - Mitigation: chay integration production-like + add timeboxed watchdog assertions.
- Risk: diff hydration fileChange drift.
  - Mitigation: run fileschanged parity fixtures + hydrate tests.

