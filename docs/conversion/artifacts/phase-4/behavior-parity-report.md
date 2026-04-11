# Phase 4 Behavior Parity Report

Date: 2026-04-10  
Owner: PTM Core Team

## Scope

Parity validation for workflow service cutover to V3 core:

- finish-task execution flow
- execution/audit workflow control-plane actions
- workflow state/events control-plane route ownership

## Locked Invariants Checked

- Public route paths unchanged for existing APIs.
- Envelope/error contract preserved (`ok/data` and `ok=false/error/details={}`).
- Legacy transcript invariant preserved:
  - production execution/audit path does not mutate `chat_state_store` transcripts.
- Workflow invalidation reasons still emitted for:
  - `execution_started`, `execution_completed`
  - `auto_review_started`, `auto_review_completed`
  - `review_rollup_started`, `review_rollup_completed`
- `/v3` control-plane endpoints are active in `workflow_v3.py`:
  - workflow state
  - workflow actions
  - project events

## Expected Internal Shift (Non-breaking)

- V3 execution snapshots now store file-change semantic events as native V3 `diff` items (metadata `semanticKind=fileChange`) instead of V2-style `toolType=fileChange` entries.
- Integration assertions were updated to accept canonical V3 representation while preserving user-facing behavior checks.

## Test Evidence

- `python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_phase4_main_wiring.py backend/tests/unit/test_phase4_workflow_v3_control_plane_guards.py backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_review_service.py backend/tests/integration/test_chat_v3_api_execution_audit.py backend/tests/integration/test_phase6_execution_audit_cutover.py`
  - Result: `84 passed`

## Conclusion

Phase 4 parity is accepted for locked behavior contract scope. Production workflow services now operate on V3 core semantics without user-facing contract regression.
