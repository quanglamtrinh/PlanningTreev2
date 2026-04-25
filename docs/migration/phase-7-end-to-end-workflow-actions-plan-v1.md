# Workflow V2 Phase 7 End-to-End Workflow Actions Plan v1

Phase 7 turns the Phase 6 Breadcrumb cutover into a verified end-to-end
Workflow V2 product path. The target is not just that the UI calls V4 routes,
but that each workflow action creates or reuses the correct Session V2 thread,
starts or completes the correct turn, persists canonical Workflow V2 state, and
refreshes the Breadcrumb UI through Workflow V2 events.

Status: implemented.

Implementation notes:

- Ask lane now exposes a Workflow V2 "Start Ask Thread" action when
  `threads.askPlanning` is missing, and the controller calls
  `ensureThread(..., "ask_planning")`.
- Breadcrumb V2 now has a package lane backed by `threads.packageReview`.
- Workflow V2 exposes `POST /v4/projects/{projectId}/nodes/{nodeId}/package-review/start`.
- `ExecutionAuditOrchestratorV2.start_package_review` ensures the
  `package_review` thread, injects package review context, starts a Session V2
  turn, persists canonical Workflow V2 state, and publishes Workflow V2 action
  and state events.
- Execution and audit `turn/completed` settlement remain owned by
  `ExecutionAuditOrchestratorV2.handle_session_event`.

## Starting Point

Assumptions:

- Phase 6 is complete.
- Breadcrumb V2 active path uses `useSessionFacadeV2`, `useWorkflowStateV2`,
  `useWorkflowEventBridgeV2`, and `workflowThreadLaneV2`.
- Existing V4 execution/audit routes exist:
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/ensure`
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/start`
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done`
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve`
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/start`
  - `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/accept`
- Execution and audit completion are driven by Session V2 turn completion events
  handled by `ExecutionAuditOrchestratorV2.handle_session_event`.
- `start_package_review` is still a planned orchestrator method and is not yet
  implemented as a V4 route.

Phase 7 closed these gaps:

- Ask planning thread creation is now a first-class Breadcrumb V2 action when
  the Workflow V2 state has no `threads.askPlanning` binding.
- Execution/audit action routes retain focused backend coverage, and Breadcrumb
  action wiring is covered through Workflow V2 store/controller tests.
- Package review now has a V4 action route, frontend action command, and
  Breadcrumb package lane.
- Context rebase is deliberately out of scope for this phase except for
  verifying that stale context blocks normal actions with `rebase_context`.

## Goal

Complete and verify these end-to-end action flows:

- Ensure ask planning thread.
- Start execution.
- Complete execution from Session V2 turn completion.
- Mark done from execution.
- Start audit.
- Complete audit from Session V2 review/audit completion.
- Improve in execution from audit decision.
- Mark done from audit.
- Start package review.

For each flow, prove:

- Frontend dispatches only V4 workflow routes for workflow actions.
- Backend owns thread binding, context injection, action authorization,
  idempotency, and state transitions.
- Session transcript and pending-request behavior remain Session Core V2.
- Workflow state refresh comes from Workflow V2 read/events, not V3 workflow
  state or mutation endpoints.

## Non-goals

- Do not move workflow business behavior into `/v4/session/*`.
- Do not remove V3 routes or compatibility adapters.
- Do not migrate project snapshot, node detail, or document editor APIs.
- Do not implement context rebase UX; Phase 8 owns
  `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`.
- Do not refactor artifact generation/confirmation workflows; Phase 9 owns
  artifact orchestrator alignment.
- Do not introduce a new frontend workflow state model. Continue using
  `WorkflowStateV2`.

## Action Contract

| User action | V4 route | Backend owner | Completion signal |
| --- | --- | --- | --- |
| Ensure ask planning | `POST /v4/projects/{projectId}/nodes/{nodeId}/threads/ask_planning/ensure` | `ThreadBindingServiceV2` | `workflowState.threads.askPlanning` |
| Start execution | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/start` | `ExecutionAuditOrchestratorV2.start_execution` | Session `turn/completed` -> `execution_completed` |
| Mark done from execution | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done` | `ExecutionAuditOrchestratorV2.mark_done_from_execution` | Workflow phase `done` |
| Start audit | `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/start` | `ExecutionAuditOrchestratorV2.start_audit` | Session/review completion -> `review_pending` |
| Improve in execution | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve` | `ExecutionAuditOrchestratorV2.request_improvements` | Session `turn/completed` -> `execution_completed` |
| Mark done from audit | `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/accept` | `ExecutionAuditOrchestratorV2.accept_audit` | Workflow phase `done` |
| Start package review | `POST /v4/projects/{projectId}/nodes/{nodeId}/package-review/start` | `ExecutionAuditOrchestratorV2.start_package_review` or a package review orchestrator | Session/review completion -> package review decision |

`audit/request-changes` remains a separate audit-decision endpoint from the API
contract. It should not replace the current Breadcrumb "Improve in Execution"
button in Phase 7 unless the UI explicitly adds a separate audit decision step.

## Work Plan

### 1. Harden Workflow V2 state machine and models for complete action coverage

Update `backend/business/workflow_v2/models.py` and
`backend/business/workflow_v2/state_machine.py` only as needed:

- Confirm all phases needed by execution/audit/package review are represented.
- Confirm `derive_allowed_actions` exposes:
  - `start_execution` from `ready_for_execution`.
  - `review_in_audit` and `mark_done_from_execution` from
    `execution_completed`.
  - `improve_in_execution` and `mark_done_from_audit` from `review_pending` or
    `audit_needs_changes`.
  - `start_package_review` only when package review prerequisites are satisfied.
  - `rebase_context` as the only action when context is stale.
- Add state-machine tests for package review allowed actions and stale-context
  blocking if they do not exist.

Do not add direct Session Core dependencies to the state machine.

### 2. Make ask planning thread ensure a first-class UI path

Backend:

- Keep `ThreadBindingServiceV2.ensure_thread` as the only code path that decides
  create/reuse/rebase for `ask_planning`.
- Ensure the V4 route returns a canonical `workflowState` after binding so the
  frontend can hydrate without guessing.

Frontend:

- Use the existing `ensureThread` command from `useWorkflowStateV2`.
- If the active ask lane has no `threads.askPlanning`, render an action in the
  workflow strip such as "Start Ask Thread".
- After ensuring the thread, select it through `useSessionFacadeV2.selectThread`.
- Keep composer disabled until the Session V2 thread is selected and ready.

Tests:

- Unit test `workflowThreadLaneV2` for missing ask thread action derivation.
- Breadcrumb integration test for missing ask thread -> ensure route -> composer
  enabled after state hydrate.

### 3. Verify execution start through turn completion

Backend:

- Add route/integration tests proving `execution/start`:
  - ensures the execution thread through Workflow V2 thread binding,
  - starts a Session V2 turn with the workflow-owned prompt,
  - stores `activeExecutionRunId` and `threads.execution`,
  - returns `workflowState` or a reloadable accepted response,
  - is idempotent for the same payload and conflicts for changed payload.
- Add tests for `handle_session_event` turning the matching Session V2
  `turn/completed` event into `execution_completed` with
  `decisions.execution.candidateWorkspaceHash`.
- Add a negative test proving unrelated Session V2 turn completions do not
  mutate Workflow V2 state.

Frontend:

- Keep execution composer disabled for business execution lanes.
- Ensure the "Start Execution" action navigates/selects the execution thread and
  shows the Session V2 transcript after the thread is ready.

### 4. Verify execution decision actions

Mark done from execution:

- Confirm the UI sends `decisions.execution.candidateWorkspaceHash` as
  `expectedWorkspaceHash`.
- Confirm backend rejects stale or mismatched workspace hash with
  `ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT`.
- Confirm success transitions to `done`, publishes Workflow V2 events, and sends
  Breadcrumb back to the graph surface.

Review in audit:

- Confirm the UI sends the same execution workspace guard into `audit/start`.
- Confirm backend ensures the audit thread, injects audit context, and starts
  the audit/review turn.
- Confirm state moves to `audit_running` and later to `review_pending` when the
  audit completion event arrives.

Tests:

- Backend route tests for success, idempotency replay, guard conflict, and event
  publication.
- Breadcrumb integration tests for button enablement, navigation, and refresh.

### 5. Verify audit decision actions

Improve in execution:

- Confirm UI sends `decisions.audit.reviewCommitSha` as
  `expectedReviewCommitSha`.
- Confirm backend checks git/workspace head, starts an execution improvement
  turn, and transitions back to `executing`.
- Confirm completion returns to `execution_completed` with a new execution
  decision.

Mark done from audit:

- Confirm UI sends the same review commit guard into `audit/accept`.
- Confirm backend transitions to `done`, preserves accepted SHA, and publishes
  Workflow V2 events.

Tests:

- Backend integration tests for success, idempotency replay, review-SHA
  conflict, and event publication.
- Frontend tests for navigation back to execution after improve and graph after
  audit accept.

### 6. Implement the package review vertical slice

Backend:

- Add `POST /v4/projects/{projectId}/nodes/{nodeId}/package-review/start`.
- Implement `ExecutionAuditOrchestratorV2.start_package_review` or split a
  dedicated package review orchestrator if that is cleaner.
- Use `ThreadBindingServiceV2.ensure_thread` for `package_review`.
- Build a minimal package review context packet from parent and child rollup
  data already available in the project/workflow stores.
- Start the package review turn through Session Core V2.
- Persist package review run ids and thread binding in Workflow V2 state.
- Publish `workflow/action_completed` or `workflow/action_failed`, plus
  `workflow/state_changed` when state changes.

Frontend:

- Extend `WorkflowStateV2` only if the backend response needs explicit package
  review decision fields beyond `threads.packageReview`.
- Add a package-review lane only if product routing already has a natural place
  for it. Otherwise, keep the existing three-lane Breadcrumb UI and expose the
  package-review action from the appropriate parent/summary surface.
- Add `startPackageReviewV2` to the Workflow V2 API client/store/hook.
- Add action derivation for `start_package_review`.

Scope guard:

- Do not implement full artifact orchestrator behavior here. Phase 7 package
  review should prove the workflow/session loop; Phase 9 can improve the
  source artifact model.

### 7. Add end-to-end style verification

Create a focused test layer that exercises full flows without relying on a real
Codex process:

- Backend integration tests with fake Session Core manager/protocol:
  - ask thread ensure,
  - execution start -> synthetic turn completion,
  - audit start -> synthetic completion,
  - improve execution -> synthetic completion,
  - package review start,
  - stale context blocks normal actions.
- Frontend integration tests with mocked V4 fetch/EventSource:
  - missing ask thread ensure,
  - execution start action,
  - review in audit action,
  - improve in execution action,
  - mark done actions,
  - package review action if exposed in Breadcrumb.
- Optional Playwright smoke only after the mocked tests are stable.

The test goal is deterministic contract coverage, not model output quality.

### 8. Add Phase 7 guard script

Add `scripts/check_workflow_v2_phase7.py`:

- Assert the Breadcrumb V2 active path has no V3 workflow state, event, or
  mutation imports.
- Assert Workflow V2 frontend client/store exposes all Phase 7 actions,
  including `ensureThread` and `startPackageReview` once implemented.
- Assert `backend/routes/workflow_v4.py` exposes package review start.
- Assert `/v4/session/*` route code remains workflow-business-free.
- Assert tests or fixtures cover `handle_session_event` completion for
  execution and audit.

## Acceptance Gates

Grep gates:

```powershell
rg -n "useWorkflowStateStoreV3|useWorkflowEventBridgeV3|resolveWorkflowProjection" frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
rg -n "/v3/projects/.*/workflow" frontend/src/features/workflow_v2 frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
rg -n "start_package_review|package-review/start" backend/business/workflow_v2 backend/routes/workflow_v4.py frontend/src/features/workflow_v2 frontend/src/features/conversation
```

Expected result:

- First two commands have no matches.
- Third command shows the implemented V2 backend route/orchestrator and
  frontend action path.

Focused tests:

```powershell
python -m pytest backend/tests/unit/test_workflow_v2_state_machine.py backend/tests/unit/test_workflow_v2_thread_binding.py backend/tests/unit/test_workflow_v2_repository.py backend/tests/integration/test_workflow_v4_phase5.py backend/tests/integration/test_workflow_v4_phase7.py
Push-Location frontend; npx vitest run tests/unit/workflowStateStoreV2.test.ts tests/unit/workflowEventBridgeV2.test.tsx tests/unit/workflowThreadLaneV2.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx tests/unit/BreadcrumbChatViewV2.workflow-v2.integration.test.tsx tests/unit/phase7.end-to-end-workflow-actions.test.ts; Pop-Location
python scripts/check_workflow_v2_phase6.py
python scripts/check_workflow_v2_phase7.py
```

Smoke checks:

- Open `/projects/{projectId}/nodes/{nodeId}/chat-v2?thread=ask` on a node with
  no ask planning binding and ensure the ask thread from the UI.
- Start execution and confirm the execution lane selects the Workflow V2
  execution thread.
- Complete the fake or real execution turn and confirm `execution_completed`
  state appears through Workflow V2 refresh.
- Review in audit and confirm the audit lane transcript comes from Session V2.
- Improve in execution and confirm the UI returns to the execution lane.
- Mark done from execution and mark done from audit both return to graph and
  leave canonical state as `done`.
- Start package review and confirm `threads.packageReview` is bound.

## Rollback

- Keep V3 compatibility routes intact.
- Keep package review additions behind V4 Workflow V2 routes and Workflow V2 UI
  action derivation.
- If package review blocks the phase, land execution/audit end-to-end gates
  first and keep package review disabled behind `start_package_review` not being
  present in `allowedActions`.
- Do not delete or rewrite Session V2 thread history during rollback.

## Done Criteria

- All listed execution/audit actions work end-to-end through Breadcrumb V2,
  Workflow V2, and Session Core V2.
- Ask planning thread can be ensured from the new UI path when absent.
- Package review has a V4 start route and a verified Session V2 thread binding.
- Workflow V2 events refresh the UI after action completion/failure.
- Stale context blocks normal actions and exposes only `rebase_context`.
- `/v4/session/*` remains session-only.
- Phase 6 and Phase 7 guard scripts pass.
