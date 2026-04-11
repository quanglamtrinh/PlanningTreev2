# Phase 4 -> Phase 5 Handoff

Date: 2026-04-10  
From: Conversion Phase 4 (Workflow Services Cutover)  
To: Conversion Phase 5 (Frontend Control Plane V3)

## 1. Phase 4 close summary

Phase 4 is closed with workflow service production path cut over to V3 core and `/v3` workflow control-plane routes active.

- Added active `/v3` workflow control-plane endpoints in `backend/routes/workflow_v3.py`:
  - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution`
  - `GET /v3/projects/{project_id}/events`
- Service dependency cutover completed for production flow:
  - `FinishTaskService`
  - `ExecutionAuditWorkflowService`
  - `ReviewService`
  now use V3 runtime/query semantics (no production reliance on private V2 query internals).
- Gate hardening completed:
  - `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED` parser added in `backend/config/app_config.py` (default `true`).
- Production wiring no longer depends on `RelayingConversationEventBrokerV2`.
- Canonical app-state service aliasing applied:
  - canonical `execution_audit_workflow_service`
  - compat alias `execution_audit_workflow_service_v2` -> same instance.

Artifacts published in Phase 4:

- `docs/conversion/artifacts/phase-4/service-call-graph-before-after.md`
- `docs/conversion/artifacts/phase-4/behavior-parity-report.md`

Verification evidence:

- `python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_phase4_main_wiring.py backend/tests/unit/test_phase4_workflow_v3_control_plane_guards.py backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_review_service.py backend/tests/integration/test_chat_v3_api_execution_audit.py backend/tests/integration/test_phase6_execution_audit_cutover.py backend/tests/integration/test_phase5_execution_audit_rehearsal.py`
  - result: `86 passed`

## 2. Locked boundaries for Phase 5

1. Frontend control-plane endpoint ownership is now stable on `/v3`:
- Phase 5 must consume only the locked endpoints in `docs/conversion/workflow-v3-control-plane-contract.md` on the active path.

2. Public contract stability remains required:
- Keep backend route paths and error envelope semantics unchanged.
- Do not introduce new frontend dependency on `/v2` workflow endpoints.

3. Naming migration sequence remains enforced:
- `threadRole` is canonical on active V3 path.
- Phase 5 objective includes removing active-path `lane` reads in FE workflow/transcript path.
- Hard cleanup/removal of lane emit/types remains Phase 7 scope.

4. Compatibility guardrail:
- `/v2` routes and `_v2` aliases remain compatibility paths during transition and must not be re-promoted to primary FE path.

## 3. Phase 5 execution focus

- Migrate frontend workflow state/action/event bridge to the active `/v3` control-plane endpoints.
- Remove primary-path usage of:
  - `buildWorkflowStatePathV2`
  - `buildWorkflowActionPathV2`
  - `buildProjectEventsUrlV2`
- Replace `workflowStateStoreV2` active dependencies with V3 store wiring.
- Remove active-path `lane` reads and use canonical `threadRole`.
- Keep reconnect-safe event handling for `GET /v3/projects/{project_id}/events`.

## 4. Entry checklist for Phase 5 PRs

1. Keep changes FE-focused; avoid backend contract changes unless strictly necessary.
2. Validate no active FE workflow calls to `/v2/projects/.../workflow*` or `/v2/projects/.../events`.
3. Preserve UX behavior parity for gating/actions in `chat-v2` primary surface.
4. Publish Phase 5 artifacts:
   - `docs/conversion/artifacts/phase-5/frontend-migration-checklist.md`
   - `docs/conversion/artifacts/phase-5/frontend-regression-notes.md`
5. Run and record verification:
   - `npm run typecheck --prefix frontend`
   - `npm run test:unit --prefix frontend`
   - FE grep gates for residual V2 workflow API references on active path.
