# Workflow V2 Phase 6 Breadcrumb Cutover Plan v1

Phase 6 cuts the Breadcrumb V2 frontend workflow surface from the legacy V3
workflow store to Workflow V2. Session Core V2 remains the conversation/runtime
owner.

Status: implemented.

Implementation notes:

- `useBreadcrumbConversationControllerV2` now reads workflow state and events
  through Workflow V2, derives lane bindings from `WorkflowStateV2`, and
  dispatches execution/audit actions through V4 workflow routes.
- Session transcript, composer, model selection, pending request overlays,
  interrupt, resolve, and reject remain owned by `useSessionFacadeV2`.
- Legacy V3 workflow routes and non-Breadcrumb V3 workflow entry points remain
  in place for later phases.

## Starting Point

Assumptions:

- Phases 0 through 5 are complete.
- `backend/routes/workflow_v4.py` exposes V4 workflow read, event, thread ensure,
  execution, and audit endpoints.
- `backend/business/workflow_v2` owns the migrated execution/audit business
  transitions.
- `frontend/src/features/workflow_v2` exists, but the current frontend layer is
  read/event oriented.
- `useBreadcrumbConversationControllerV2` still imports V3 workflow state,
  V3 workflow events, V3 projection helpers, and V3 workflow mutations.

Current active-path split:

- Keep: `useSessionFacadeV2`, Session V2 transcript, composer, model selection,
  pending request overlays, stream/gap handling, and interrupt behavior.
- Replace: workflow state loading, workflow invalidation events, workflow action
  derivation, workflow thread role selection, and workflow mutations.

## Goal

Breadcrumb V2 should use Workflow V2 for workflow business state and actions:

- Read workflow state from
  `GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state`.
- Refresh workflow state through `GET /v4/projects/{projectId}/events`.
- Select Session V2 threads from V2 role bindings.
- Dispatch execution/audit actions through V4 workflow mutation routes.
- Stop importing V3 workflow store, V3 workflow event bridge, V3 workflow
  projection, or V3 workflow mutation functions in the Breadcrumb V2 path.

## Non-goals

- Do not remove V3 routes.
- Do not migrate project snapshot, node detail, frame/spec document, or artifact
  APIs just to complete this phase.
- Do not move workflow business behavior into `/v4/session/*`.
- Do not finish package review or context rebase UX in this phase.
- Do not require `NodeDocumentEditor` finish-task migration for the Breadcrumb
  cutover gate. That call site can remain a separately tracked workflow entry
  point unless Phase 6 explicitly expands scope.

## Route And Action Mapping

Thread lane mapping:

| Breadcrumb lane | Workflow V2 role | V2 state field |
| --- | --- | --- |
| `ask` | `ask_planning` | `threads.askPlanning` |
| `execution` | `execution` | `threads.execution` |
| `audit` | `audit` | `threads.audit` |

Workflow action mapping:

| V2 action | Route | Required guard |
| --- | --- | --- |
| `start_execution` | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/start` | none beyond idempotency, optional model fields |
| `review_in_audit` | `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/start` | `decisions.execution.candidateWorkspaceHash` |
| `mark_done_from_execution` | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done` | `decisions.execution.candidateWorkspaceHash` |
| `improve_in_execution` | `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve` | `decisions.audit.reviewCommitSha` |
| `mark_done_from_audit` | `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/accept` | `decisions.audit.reviewCommitSha` |
| `rebase_context` | Phase 8 | hide or render as unavailable in Phase 6 |
| `start_package_review` | later package-review phase | hide or render as unavailable in Phase 6 |

## Work Plan

### 1. Complete the Workflow V2 frontend API client

Update `frontend/src/features/workflow_v2/api/client.ts`:

- Add response types for V4 workflow mutations. The common shape should support
  `{ workflowState }` plus optional async ids such as `accepted`, `threadId`,
  `turnId`, `auditRunId`, `reviewCycleId`, and `reviewCommitSha`.
- Add idempotent mutation calls:
  - `ensureWorkflowThreadV2`
  - `startExecutionV2`
  - `markDoneFromExecutionV2`
  - `startAuditV2`
  - `improveExecutionV2`
  - `acceptAuditV2`
- Keep auth/header behavior consistent with `getWorkflowStateV2`.
- Normalize `WorkflowV2ApiError` details so the controller can surface
  deterministic workflow errors without special-casing fetch failures.

### 2. Promote the Workflow V2 store from read-only to action-capable

Update `frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts`:

- Add `activeMutations: Record<string, WorkflowMutationActionV2 | null>`.
- Add mutation methods matching the V4 action routes.
- Generate idempotency keys in the store, mirroring the V3 store pattern.
- On mutation success, prefer `response.workflowState`; if the backend returns an
  accepted response without state, reload `workflow-state`.
- On mutation failure, record the error under the node key and clear the active
  mutation in `finally`.
- Keep the existing in-flight load dedupe.

Update `frontend/src/features/workflow_v2/hooks/useWorkflowStateV2.ts`:

- Return `activeMutation` and the V2 mutation commands needed by Breadcrumb.
- Keep the hook small; action derivation should live in a projection helper, not
  inside the store hook.

Update `frontend/src/features/workflow_v2/hooks/useWorkflowEventBridgeV2.ts`:

- Refresh on `workflow/state_changed`, `workflow/context_stale`,
  `workflow/action_completed`, and `workflow/action_failed` for the active node.
- Continue filtering by `projectId` and `nodeId`.

### 3. Add a Workflow V2 lane projection helper

Add `frontend/src/features/conversation/workflowThreadLaneV2.ts` or split the
existing projection into explicit V2/V3 helpers.

The V2 helper should:

- Consume `WorkflowStateV2`, not `NodeWorkflowView`.
- Resolve lane thread ids from V2 role bindings.
- Derive action buttons from `allowedActions` and V2 decision guard fields.
- Preserve existing labels where possible:
  - `review_in_audit`: "Review in Audit"
  - `mark_done_from_execution`: "Mark Done"
  - `improve_in_execution`: "Improve in Execution"
  - `mark_done_from_audit`: "Mark Done"
  - `start_execution`: "Start Execution" if Breadcrumb owns that entry point in
    Phase 6.
- Return action payloads that already contain the expected workspace hash or
  review commit SHA when required.
- Keep review nodes read-only.
- Build Session V2 turn policy from selected model, provider, and project path
  only for lanes where direct Session composer submission remains valid.

Composer policy note:

- Ask lane can continue using Session V2 composer when an ask-planning thread is
  available.
- Execution and audit business transitions should go through V4 workflow
  actions. If Workflow V2 does not yet expose a business endpoint for a freeform
  execution follow-up, keep that composer path disabled rather than starting a
  business execution turn directly through `/v4/session/*`.

### 4. Rewrite the Breadcrumb controller imports and data flow

Update `frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx`:

- Replace `useWorkflowStateStoreV3` with `useWorkflowStateV2` or selectors from
  `useWorkflowStateStoreV2`.
- Replace `useWorkflowEventBridgeV3` with `useWorkflowEventBridgeV2`.
- Replace `resolveWorkflowProjection` with the V2 lane projection helper.
- Replace V3 mutation calls with V2 store commands.
- Keep project snapshot and node detail stores for route validation,
  `isReviewNode`, detail pane rendering, and `projectPath` until those APIs get
  their own migration contract.
- Keep `useSessionFacadeV2` as the only source for session connection, active
  thread, active turns, active items, model selection, pending requests, submit,
  interrupt, resolve, and reject.
- Select the active Session V2 thread from the projected V2 lane thread id.
- Scope pending request overlays to the selected V2 lane thread, as today.

Navigation after actions:

- `start_execution`: stay or navigate to `thread=execution`.
- `review_in_audit`: navigate to `thread=audit`.
- `improve_in_execution`: navigate to `thread=execution`.
- `mark_done_from_execution` and `mark_done_from_audit`: return to graph, matching
  current behavior.

### 5. Update tests and guard scripts

Frontend tests:

- Extend `workflowStateStoreV2.test.ts` for mutation idempotency keys,
  `activeMutations`, response-state hydration, reload fallback, and error
  handling.
- Extend `workflowEventBridgeV2.test.tsx` to refresh on action-completed and
  action-failed events.
- Add `workflowThreadLaneV2.test.ts` for lane id resolution, action derivation,
  guard extraction, and read-only review nodes.
- Update Breadcrumb tests to mock Workflow V2 state/store instead of V3 workflow
  state/store.
- Keep tests proving pending request overlays and Session V2 composer wiring are
  still delegated to `useSessionFacadeV2`.

Guard script:

- Add `scripts/check_workflow_v2_phase6.py`.
- Gate the new Breadcrumb path against:
  - `useWorkflowStateStoreV3`
  - `useWorkflowEventBridgeV3`
  - `resolveWorkflowProjection` from the V3 helper
  - `reviewInAudit`, `markDoneFromExecution`, `improveInExecution`,
    `markDoneFromAudit` V3 store commands
  - `/v3/projects/.*/workflow` in Workflow V2 frontend code
- Allow documented legacy/test-only matches outside the Breadcrumb V2 path.

## Acceptance Gates

Grep gates:

```powershell
rg -n "useWorkflowStateStoreV3|useWorkflowEventBridgeV3|resolveWorkflowProjection" frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
rg -n "reviewInAudit|markDoneFromExecution|improveInExecution|markDoneFromAudit" frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
rg -n "/v3/projects/.*/workflow" frontend/src/features/workflow_v2 frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
```

Expected result: no matches.

Focused tests:

```powershell
Push-Location frontend; npx vitest run tests/unit/workflowStateStoreV2.test.ts tests/unit/workflowEventBridgeV2.test.tsx tests/unit/workflowThreadLaneV2.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx tests/unit/BreadcrumbChatViewV2.workflow-v2.integration.test.tsx tests/unit/phase6.active-path-v2.guards.test.ts tests/unit/sessionV2.BreadcrumbChatViewV2.shell-gate.test.ts; Pop-Location
python -m pytest backend/tests/unit/test_workflow_v2_state_machine.py backend/tests/unit/test_workflow_v2_repository.py backend/tests/integration/test_workflow_v4_phase5.py
python scripts/check_workflow_v2_phase6.py
```

Smoke checks:

- Open `/projects/{projectId}/nodes/{nodeId}/chat-v2?thread=ask`.
- Confirm Breadcrumb loads V2 workflow state and selects `threads.askPlanning`.
- Switch to execution and audit lanes; active transcripts come from Session V2.
- Trigger Review in Audit, Improve in Execution, and Mark Done actions from the
  action strip against V4 workflow routes.
- Confirm workflow refresh comes from `/v4/projects/{projectId}/events`.
- Confirm Session pending request overlays still resolve through
  `/v4/session/requests/*`.

## Rollback

- Keep V3 workflow routes and compatibility adapters available.
- Keep Phase 6 changes localized to `workflow_v2` frontend modules and
  `useBreadcrumbConversationControllerV2`.
- If a runtime blocker appears, revert the controller to the V3 workflow imports
  while keeping V2 client/store tests in place.
- Do not rewrite or delete legacy workflow state as part of rollback.

## Done Criteria

- Breadcrumb V2 workflow read, events, action strip, and workflow mutations are
  V2-only.
- Breadcrumb V2 session runtime behavior still comes from Session Core V2.
- No V3 workflow imports remain in `useBreadcrumbConversationControllerV2`.
- Project snapshot and node detail V3 reads are either unchanged or explicitly
  documented as out of Phase 6 scope.
- Phase 6 guard script and focused tests pass.
