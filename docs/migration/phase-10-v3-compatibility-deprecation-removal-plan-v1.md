# Workflow V2 Phase 10 V3 Compatibility, Deprecation, and Removal Plan v1

Phase 10 turns the remaining workflow V3 surface from a hybrid legacy service
into an explicit compatibility layer over Workflow Core V2. Phases 6-9 moved
the active Breadcrumb workflow path, execution/audit actions, context rebase,
and artifact decisions to Workflow V2. Phase 10 now makes that ownership
unambiguous: V3 may remain as an adapter for legacy callers, but it must not
own workflow business state or transitions.

Status: complete.

## Starting Point

Assumptions:

- Phase 9 is complete.
- Breadcrumb V2 uses `useSessionFacadeV2`, `useWorkflowStateV2`,
  `useWorkflowEventBridgeV2`, and `workflowThreadLaneV2`.
- Workflow V2 owns execution/audit orchestration, thread binding, context
  packets, context stale/rebase, artifact orchestration, V4 workflow routes,
  and V4 artifact routes.
- Session Core V2 remains the conversation/runtime plane under
  `/v4/session/*`.

Current repo shape:

- `backend/routes/workflow_v3.py` still exposes the legacy V3 workflow routes
  under the `/v3` API prefix.
- The V3 workflow routes still call `app.state.execution_audit_workflow_service`
  through `_workflow_service(...)`.
- `ExecutionAuditWorkflowService` now prefers
  `_workflow_orchestrator_v2` for the main execution/audit actions, but it still
  contains old fallback business implementations that mutate
  `storage.workflow_state_store`.
- `ExecutionAuditOrchestratorV2.get_legacy_workflow_state(...)` and
  `legacy_workflow_state_view(...)` already provide the main V2-to-V3 response
  converter.
- `WorkflowStateRepositoryV2` reads canonical
  `.planningtree/workflow_core_v2` state and can read-through convert legacy
  `.planningtree/workflow_v2` state.
- `frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx`
  is on the V2 workflow path.
- `frontend/src/features/node/NodeDocumentEditor.tsx` still imports
  `useWorkflowStateStoreV3` for `finishTask`.
- `workflowStateStoreV3`, `workflowEventBridgeV3`, V3 thread-by-id routes, and
  Messages V3 modules still exist for legacy/conversation compatibility.

## Goal

Make Workflow Core V2 the only business owner for workflow state and workflow
actions:

- Move V3 workflow compatibility into an explicit adapter module.
- Rewire V3 workflow read/mutation routes to that adapter.
- Preserve old V3 response shapes for legacy callers while sourcing all data and
  transitions from Workflow V2.
- Remove or fail closed the legacy execution/audit fallback branches in
  `ExecutionAuditWorkflowService`.
- Cut remaining active frontend workflow entry points away from V3 workflow
  store/mutation APIs.
- Add deprecation headers, telemetry, and guard scripts so V3 usage can be
  measured before route removal.
- Keep `/v4/session/*` session-only and keep Workflow V2 business behavior in
  workflow services/routes.

## Non-goals

- Do not remove general `/v3` project, node, document, workspace, or snapshot
  APIs in this phase.
- Do not remove legacy conversation/thread rendering modules such as
  `MessagesV3` or the V3 thread-by-id store unless the active dependency scan
  proves a workflow-only endpoint is unused.
- Do not destructively rewrite legacy workflow state files. Read-through
  migration into canonical V2 state remains the safe path.
- Do not move workflow compatibility behavior into `/v4/session/*`.
- Do not change public V4 workflow or artifact contracts except to add telemetry
  needed for deprecation.
- Do not remove V3 routes before tests and telemetry show there is no active
  product dependency.

## Compatibility Contract

The V3 workflow compatibility layer should preserve the old success envelope:

```json
{
  "ok": true,
  "data": { "...": "legacy V3 shape" }
}
```

Legacy workflow state must keep these fields for compatibility:

- `workflowPhase`
- `askThreadId`
- `executionThreadId`
- `auditLineageThreadId`
- `reviewThreadId`
- `activeExecutionRunId`
- `latestExecutionRunId`
- `activeReviewCycleId`
- `latestReviewCycleId`
- `currentExecutionDecision`
- `currentAuditDecision`
- `acceptedSha`
- `runtimeBlock`
- `canSendExecutionMessage`
- `canReviewInAudit`
- `canImproveInExecution`
- `canMarkDoneFromExecution`
- `canMarkDoneFromAudit`

Route mapping:

| Legacy V3 route | Workflow V2 owner | Response conversion |
| --- | --- | --- |
| `GET /v3/projects/{projectId}/nodes/{nodeId}/workflow-state` | `ExecutionAuditOrchestratorV2.get_legacy_workflow_state` | Return legacy state fields in V3 envelope |
| `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/finish-task` | `start_execution` | Return `accepted`, `threadId`, `turnId`, `executionRunId`, `workflowPhase` |
| `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/mark-done-from-execution` | `mark_done_from_execution` | Return legacy state fields |
| `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/review-in-audit` | `start_audit` | Return `accepted`, `reviewCycleId`, `reviewThreadId`, `workflowPhase` |
| `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/improve-in-execution` | `request_improvements` | Return `accepted`, `threadId`, `turnId`, `executionRunId`, `workflowPhase` |
| `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/mark-done-from-audit` | `accept_audit` | Return legacy state fields |

Event compatibility:

- `GET /v3/projects/{projectId}/events` may remain as a legacy SSE endpoint
  during Phase 10.
- If legacy workflow clients still depend on it, project Workflow V2 events into
  the old `node.workflow.updated` / `node.detail.invalidate` style payloads.
- If no workflow client depends on it, mark the route deprecated and keep it
  read-only until removal.
- Do not mix Workflow V2 events into Session Core V2 thread event streams.

Deprecation metadata:

- Add response headers to V3 workflow compatibility responses:
  - `Deprecation: true`
  - `X-PlanningTree-Deprecated-Surface: workflow-v3`
  - `X-PlanningTree-Replacement-Surface: workflow-v2`
- Do not set a hard `Sunset` date until telemetry confirms no active dependency
  or the product team has chosen a removal date.
- Log a structured event for every V3 workflow route hit with route name,
  project id, node id, caller surface when available, and whether the request was
  read-only or mutating.

## Work Plan

### 1. Inventory and allowlist remaining V3 workflow dependencies

Create a Phase 10 dependency inventory before deleting code:

- Backend workflow routes in `backend/routes/workflow_v3.py`.
- Backend references to `ExecutionAuditWorkflowService` and
  `storage.workflow_state_store`.
- Frontend references to:
  - `useWorkflowStateStoreV3`
  - `useWorkflowEventBridgeV3`
  - `getWorkflowStateV3`
  - `finishTaskWorkflowV3`
  - `/v3/projects/.../workflow`
- Tests that still seed or assert legacy workflow state.

Classify each match:

- `active_product_path`: must move to V4 or the V2 store in Phase 10.
- `legacy_compat_path`: allowed while V3 compatibility routes exist.
- `test_fixture`: allowed only if the test explicitly proves compatibility.
- `unrelated_v3_surface`: project/node/document/conversation V3, out of scope
  for this workflow phase.

The initial known active product-path item is
`NodeDocumentEditor`'s `useWorkflowStateStoreV3.finishTask` call. Phase 10
should either:

- move that action to `useWorkflowStateV2.startExecution`, or
- remove/hide the editor-level finish-task action and route users through the
  Breadcrumb V2 workflow action.

Do not leave it as an active V3 workflow mutation.

### 2. Add an explicit V3 workflow adapter

Add a backend module such as:

```text
backend/business/workflow_v2/legacy_v3_adapter.py
```

Responsibilities:

- Own every V3 workflow compatibility method.
- Call `ExecutionAuditOrchestratorV2`, `WorkflowStateRepositoryV2`,
  `ThreadBindingServiceV2`, and Workflow V2 event helpers as needed.
- Convert V2 responses into legacy V3 payloads.
- Preserve idempotency behavior by forwarding idempotency keys into the V2
  orchestrator.
- Map `WorkflowV2Error` into deterministic V3-compatible error envelopes.
- Emit deprecation telemetry for each route call.

Initial methods:

- `get_workflow_state(project_id, node_id)`
- `finish_task(project_id, node_id, idempotency_key)`
- `mark_done_from_execution(project_id, node_id, idempotency_key, expected_workspace_hash)`
- `review_in_audit(project_id, node_id, idempotency_key, expected_workspace_hash)`
- `improve_in_execution(project_id, node_id, idempotency_key, expected_review_commit_sha)`
- `mark_done_from_audit(project_id, node_id, idempotency_key, expected_review_commit_sha)`
- `project_legacy_workflow_event(event)`

Move or reuse `legacy_workflow_state_view(...)` from
`execution_audit_orchestrator.py`, but keep the conversion testable without
calling route code.

### 3. Rewire V3 workflow routes to the adapter

Update `backend/routes/workflow_v3.py`:

- Add `_workflow_v3_adapter(request)` that reads
  `app.state.workflow_v3_compat_adapter`.
- Route the six workflow state/mutation endpoints through the adapter.
- Keep the public route paths and request models unchanged.
- Add the deprecation headers to successful and domain-error responses for only
  the workflow compatibility routes.
- Keep non-workflow V3 project/thread compatibility routes explicitly outside
  the adapter path unless Phase 10 inventory proves they are workflow-business
  mutations.

Update `backend/main.py`:

- Construct and store `workflow_v3_compat_adapter`.
- Stop wiring V3 workflow routes through
  `execution_audit_workflow_service` for state/mutation endpoints.
- Keep `execution_audit_workflow_service` available only for endpoints that are
  intentionally still legacy and separately tracked.

### 4. Retire legacy execution/audit fallback business code

Refactor `ExecutionAuditWorkflowService` so it is no longer a shadow business
state machine:

- Remove fallback branches for:
  - `finish_task`
  - `mark_done_from_execution`
  - `review_in_audit`
  - `improve_in_execution`
  - `mark_done_from_audit`
- If a method remains temporarily for legacy route compatibility, make it call
  the V3 adapter or Workflow V2 orchestrator directly.
- If `_workflow_orchestrator_v2` is missing, fail closed with a deterministic
  configuration error instead of executing legacy business logic.
- Move any still-needed helpers into Workflow V2 services or lower-level shared
  services.
- Keep pure utility functions only when they have active tests and no state
  mutation side effects.

After this step, execution/audit business transitions must not write
`storage.workflow_state_store`. The only allowed legacy workflow store access
should be:

- read-through conversion in `WorkflowStateRepositoryV2`,
- compatibility tests/fixtures,
- temporary audit/telemetry code explicitly allowlisted by Phase 10.

### 5. Cut remaining frontend workflow calls from V3 to V2

Update active frontend paths:

- Replace `NodeDocumentEditor`'s `useWorkflowStateStoreV3.finishTask` dependency
  with a Workflow V2 action or remove that action from the editor surface.
- Keep Breadcrumb V2 on `useWorkflowStateV2` and V4 workflow routes.
- Keep V3 workflow store/event modules only for legacy/test compatibility until
  route removal.

Guard rule:

- No production frontend workflow action should call
  `/v3/projects/{projectId}/nodes/{nodeId}/workflow-state`,
  `/workflow/finish-task`, `/workflow/mark-done-from-execution`,
  `/workflow/review-in-audit`, `/workflow/improve-in-execution`, or
  `/workflow/mark-done-from-audit`.

Project snapshot, node detail, document read/write, and legacy conversation APIs
may remain on `/v3` under the existing scope note.

### 6. Decide read-only vs mutating V3 compatibility mode

Phase 10 should support a staged rollout:

1. Adapter parity mode:
   - V3 workflow reads and mutations remain available.
   - Every mutation calls the V2 orchestrator.
   - Deprecation telemetry is emitted.
2. Read-only mode:
   - V3 `workflow-state` remains available.
   - V3 workflow mutation routes return a deterministic deprecation error unless
     an emergency compatibility flag is enabled.
3. Removal mode:
   - V3 workflow routes are removed from production routing after telemetry and
     tests confirm no dependency.

Add configuration flags only if needed:

- `WORKFLOW_V3_COMPAT_MODE=adapter|read_only|off`
- default should be `adapter` during Phase 10 implementation.

Do not apply this flag to unrelated `/v3` project/node/document/conversation
routes.

### 7. Add telemetry and deprecation reporting

Add a small telemetry sink or structured logs that can answer:

- Which V3 workflow route was called?
- Was it read-only or mutating?
- Which frontend/backend surface called it, if known?
- Did it hit adapter parity, read-only, or off mode?
- Did the adapter response come from canonical V2 state?

Add a report command or script output in the Phase 10 guard that summarizes
remaining allowed V3 workflow references. This does not need full production
analytics in the first implementation; deterministic test-visible logs or
counters are enough for the local gate.

### 8. Tests

Backend unit tests:

- Add `backend/tests/unit/test_workflow_v3_compat_adapter.py`.
- Cover legacy state conversion for every V2 phase.
- Cover action response conversion for all six V3 workflow endpoints.
- Cover idempotency replay and idempotency conflict pass-through.
- Cover `WorkflowV2Error` to V3 error-envelope conversion.
- Cover deprecation headers or response metadata helper.

Backend integration tests:

- Add `backend/tests/integration/test_workflow_v3_phase10_compat.py`.
- Cover:
  - V3 `workflow-state` reads canonical V2 state.
  - V3 `finish-task` starts execution through the V2 orchestrator.
  - V3 mark done/review/improve/accept actions mutate canonical V2 state.
  - V3 route responses keep the legacy `{ ok, data }` envelope.
  - No execution/audit business transition writes only legacy workflow state.
  - Read-only mode blocks V3 mutations while keeping `workflow-state` readable.
  - Deprecated route telemetry is emitted.

Frontend tests:

- Update `NodeDocumentEditor` tests to prove the finish-task action no longer
  imports or calls `useWorkflowStateStoreV3`.
- Keep `workflowStateStoreV3.test.ts` only as legacy compatibility coverage if
  the store remains.
- Keep Breadcrumb V2 tests proving the active path uses Workflow V2.

Regression tests:

- Existing V4 workflow tests from Phases 5-9 continue to pass.
- Existing V3 compatibility tests continue to pass, but should assert adapter
  behavior rather than legacy service ownership.

### 9. Add Phase 10 guard script

Add `scripts/check_workflow_v2_phase10.py`.

The script should assert:

- `backend/business/workflow_v2/legacy_v3_adapter.py` exists.
- V3 workflow state/mutation routes call the adapter, not
  `ExecutionAuditWorkflowService` directly.
- `ExecutionAuditWorkflowService` no longer contains fallback business branches
  that mutate `workflow_state_store` for execution/audit transitions.
- Production frontend code has no active V3 workflow state/mutation calls.
- `NodeDocumentEditor` does not import `useWorkflowStateStoreV3`.
- `/v4/session/*` remains workflow-business-free.
- V3 compatibility tests mention all six legacy workflow endpoints.
- Phase 6, Phase 7, Phase 8, and Phase 9 guard scripts still pass.

Keep an allowlist for:

- V3 compatibility adapter code.
- V3 compatibility tests.
- repository read-through conversion from legacy state.
- unrelated project/node/document/conversation V3 surfaces.

## Acceptance Gates

Grep gates:

```powershell
rg -n "workflow_v3_compat|LegacyWorkflowV3|legacy_v3_adapter" backend/business backend/routes backend/main.py
rg -n "_workflow_service\\(|ExecutionAuditWorkflowService" backend/routes/workflow_v3.py
rg -n "useWorkflowStateStoreV3|getWorkflowStateV3|finishTaskWorkflowV3|/workflow/(finish-task|mark-done-from-execution|review-in-audit|improve-in-execution|mark-done-from-audit)" frontend/src
rg -n "workflow_state_store\\.write_state" backend/services/execution_audit_workflow_service.py backend/business/workflow_v2
```

Expected result:

- First command shows the explicit adapter and route/main wiring.
- Second command has no matches in the six V3 workflow state/mutation route
  handlers after route rewiring. Matches in out-of-scope legacy by-id helpers
  must be allowlisted and separately documented.
- Third command has no matches in active production frontend workflow paths.
  Legacy compatibility modules/tests may be allowlisted.
- Fourth command has no execution/audit business fallback writes outside the V2
  repository and documented read-through migration path.

Focused tests:

```powershell
python -m pytest backend/tests/unit/test_workflow_v3_compat_adapter.py backend/tests/integration/test_workflow_v3_phase10_compat.py
Push-Location frontend; npx vitest run tests/unit/NodeDocumentEditor.test.tsx tests/unit/BreadcrumbChatViewV2.workflow-v2.integration.test.tsx tests/unit/workflowStateStoreV2.test.ts; Pop-Location
python scripts/check_workflow_v2_phase6.py
python scripts/check_workflow_v2_phase7.py
python scripts/check_workflow_v2_phase8.py
python scripts/check_workflow_v2_phase9.py
python scripts/check_workflow_v2_phase10.py
```

Regression tests:

```powershell
python -m pytest backend/tests/unit/test_workflow_v2_state_machine.py backend/tests/unit/test_workflow_v2_repository.py backend/tests/unit/test_workflow_v2_thread_binding.py backend/tests/unit/test_workflow_v2_context_rebase.py backend/tests/unit/test_workflow_v2_artifact_orchestrator.py
python -m pytest backend/tests/integration/test_workflow_v4_phase5.py backend/tests/integration/test_workflow_v4_phase7.py backend/tests/integration/test_workflow_v4_phase8.py backend/tests/integration/test_workflow_v4_phase9.py
python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py
```

Smoke checks:

- Open Breadcrumb V2 and confirm workflow state/events/actions use V4 routes.
- Start execution from Breadcrumb V2 and confirm Session V2 thread/turn behavior.
- Call V3 `workflow-state` manually and confirm it returns the legacy shape
  derived from the same canonical V2 state.
- Call a V3 mutation in adapter mode and confirm canonical V2 state changes.
- Switch V3 compatibility to read-only mode and confirm V3 mutations are blocked
  while `workflow-state` remains readable.
- Confirm deprecation headers and telemetry appear for V3 workflow calls.
- Confirm `/v4/session/*` traffic remains session-only.

## Rollback

- Keep the adapter mode as the rollback target. If read-only or removal mode
  causes a blocker, return `WORKFLOW_V3_COMPAT_MODE` to `adapter`.
- Do not restore legacy execution/audit fallback business code once removed.
  Fix adapter parity against Workflow V2 instead.
- Keep canonical V2 state untouched during rollback.
- Do not rewrite or delete legacy workflow files.
- Keep V3 route paths available until telemetry confirms removal is safe.

## Done Criteria

- V3 workflow state and mutation routes are explicit compatibility adapters over
  Workflow Core V2.
- Active frontend workflow paths do not import V3 workflow state, V3 workflow
  events, or V3 workflow mutations.
- `ExecutionAuditWorkflowService` no longer owns execution/audit business
  transitions or mutates legacy workflow state as a fallback.
- Legacy V3 response shapes and error behavior are covered by adapter tests.
- V3 workflow deprecation telemetry and headers are present.
- V3 workflow routes can be switched to read-only mode, and then removed in a
  later cleanup once telemetry confirms no active dependency.
- Phase 6, Phase 7, Phase 8, Phase 9, and Phase 10 guard scripts pass.
