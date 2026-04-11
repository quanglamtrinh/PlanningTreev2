# Phase 4 - Workflow Services Cutover

Status: completed  
Estimate: 8-10 person-days (18%)

## 1. Objective

Cut execution/audit workflow service paths over to native V3 core while preserving user-facing behavior.

## 2. In Scope

- `FinishTaskService`, `ExecutionAuditWorkflowService`, `ReviewService`
- `/v3` workflow control-plane route ownership (`workflow-state`, actions, project events)
- V3 workflow/event wiring and gate hardening
- Preserve legacy compatibility routes on `/v2` (no deletion in this phase)

## 3. Out of Scope

- Frontend control-plane migration (Phase 5)
- Hard removal of V2 modules/stores/routes (Phase 7)

## 4. Work Breakdown

- [x] Added `/v3` workflow control-plane endpoints in `backend/routes/workflow_v3.py`:
  - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution`
  - `GET /v3/projects/{project_id}/events`
- [x] Migrated production workflow service dependencies to V3 runtime/query semantics:
  - app wiring now injects `thread_runtime_service_v3` + `thread_query_service_v3`
  - removed production reliance on private query internals (`runtime_v2._query_service`)
- [x] Canonicalized workflow app state while preserving compatibility aliases:
  - canonical: `execution_audit_workflow_service`
  - compatibility alias: `execution_audit_workflow_service_v2` -> same instance
- [x] Added env-gated parser for execution/audit rollout:
  - `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED` (default `true`)
- [x] Removed V2->V3 relay from production wiring:
  - `/v3` stream path now reads canonical V3 broker wiring
- [x] Preserved legacy transcript invariant:
  - execution/audit production path does not write legacy `chat_state_store` transcripts

## 5. Deliverables

- Native V3 workflow service path for production execution/audit flows
- Active `/v3` workflow control-plane endpoint set
- Artifacts:
  - `docs/conversion/artifacts/phase-4/service-call-graph-before-after.md`
  - `docs/conversion/artifacts/phase-4/behavior-parity-report.md`

## 6. Exit Criteria

- [x] Workflow service production path no longer depends on V2 runtime/query service internals
- [x] `/v3` workflow-state/actions/events are active and pass contract coverage
- [x] Legacy `chat_state_store` execution/audit transcripts remain untouched in production flow
- [x] Regression tests pass for execution/audit cutover and V3 API behavior

## 7. Verification

- [x] `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
- [x] `python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py`
- [x] `python -m pytest -q backend/tests/unit/test_review_service.py`
- [x] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
- [x] `python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_phase4_main_wiring.py backend/tests/unit/test_phase4_workflow_v3_control_plane_guards.py`

## 8. Risks and Mitigations

- Risk: service behavior drift after runtime/query cutover.
  - Mitigation: keep parity assertions in integration path and lock action/state endpoint coverage.
- Risk: mixed-version tests/fakes fail under strict V3 thread-id semantics.
  - Mitigation: upgrade integration test doubles to UUID-shaped thread ids and patch codex injection helpers for V3 services.
