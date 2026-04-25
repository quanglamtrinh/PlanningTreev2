# Workflow V2 Phase 8 Context Stale and Rebase Plan v1

Phase 8 makes Workflow V2 context freshness explicit and repairable. Phase 7
proved the end-to-end action path through Breadcrumb V2, Workflow V2, and
Session Core V2; Phase 8 now prevents those long-lived threads from continuing
with stale frame/spec/split context after source artifacts change.

Status: complete.

## Starting Point

Assumptions:

- Phase 7 is complete.
- Breadcrumb V2 workflow actions use `useWorkflowStateV2`,
  `useWorkflowEventBridgeV2`, `workflowThreadLaneV2`, and V4 workflow routes.
- Session Core V2 remains the runtime/conversation plane under `/v4/session/*`.
- Workflow Core V2 already has partial context primitives:
  - `SourceVersions` and `ThreadBinding.contextPacketHash` in
    `backend/business/workflow_v2/models.py`.
  - deterministic `PlanningTreeContextPacket` hashes and `context_update`
    packets in `context_packets.py` and `context_builder.py`.
  - stale blocking in `state_machine.derive_allowed_actions`, where stale
    non-terminal states expose only `rebase_context`.
  - `ThreadBindingServiceV2.ensure_thread(..., force_rebase=True)`, which can
    append an update packet for a single role binding.
  - frontend `WorkflowStateV2.context` and `WorkflowActionV2.rebase_context`.

Remaining gaps:

- There is no dedicated
  `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase` endpoint.
- Context stale detection is mostly reactive when thread binding is ensured,
  not a deterministic workflow-state check after source artifacts change.
- `WorkflowStateV2.context` exposes `stale` and `staleReason`, but does not
  expose per-role stale bindings, current source versions, or target source
  versions.
- Rebase is not a single workflow action. The current `forceRebase` behavior is
  useful plumbing, but the UI should not guess which roles to rebase.
- Breadcrumb V2 does not yet render or dispatch a deterministic
  `rebase_context` action.

## Goal

Implement context stale detection and a first-class rebase workflow action:

- Pin source artifact versions in thread bindings and context packet metadata.
- Detect frame/spec/split source changes against existing role bindings.
- Expose stale details in the canonical Workflow V2 state response.
- Add `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`.
- Append context update packets to affected Session V2 threads instead of
  mutating historical context messages.
- Clear stale state only after affected bindings have been updated.
- Surface a deterministic Breadcrumb V2 "Rebase Context" action when
  `allowedActions` is `["rebase_context"]`.

## Non-goals

- Do not move workflow business behavior into `/v4/session/*`.
- Do not rewrite or delete existing Session V2 thread history.
- Do not mutate previously injected context packets.
- Do not migrate frame/spec/clarify/split orchestration into Workflow V2; Phase
  9 owns artifact orchestrator alignment.
- Do not remove V3 compatibility routes.
- Do not make the frontend choose which role bindings require rebase. The
  backend owns stale detection and rebase scope.

## Source Version Contract

Workflow V2 context source versions should remain canonical and comparable.

| Source | Field | Initial owner |
| --- | --- | --- |
| confirmed frame | `frameVersion` | `WorkflowContextBuilderV2` from frame metadata |
| confirmed spec | `specVersion` | `WorkflowContextBuilderV2` from spec metadata |
| split manifest / task context | `splitManifestVersion` | Phase 8 adds deterministic extraction or `null` with documented behavior |

Every `ThreadBinding` must keep:

- `sourceVersions`
- `contextPacketHash`
- `updatedAt`

Every injected context item must keep metadata:

- `workflowContext: true`
- `role`
- `packetKind`
- `contextPacketHash`
- `injectedPacketHash` when the item is a `context_update` wrapper around a
  next context packet.

## Public API Contract

Add:

`POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`

Request:

```json
{
  "idempotencyKey": "context-rebase:uuid",
  "expectedWorkflowVersion": 12,
  "roles": ["execution", "audit"]
}
```

Rules:

- `expectedWorkflowVersion` is optional but recommended. If supplied and it does
  not match the current Workflow V2 state version, return a deterministic
  version conflict.
- `roles` is optional. If omitted, rebase every stale bound role. If supplied,
  it must be a subset of currently bound stale roles.
- The route must be idempotent for the same payload and key. Same key with a
  different payload is a conflict.
- The route must return the canonical state after rebase.

Response:

```json
{
  "rebased": true,
  "updatedBindings": [
    {
      "role": "execution",
      "threadId": "thread_exec",
      "contextPacketHash": "sha256:new"
    }
  ],
  "workflowState": { "...": "canonical state response" }
}
```

Error cases:

- `ERR_WORKFLOW_CONTEXT_NOT_STALE` when no bound role needs rebase.
- `ERR_WORKFLOW_VERSION_CONFLICT` when `expectedWorkflowVersion` is stale.
- `ERR_WORKFLOW_CONTEXT_STALE` continues to block normal business actions while
  stale context remains.
- Existing Session Core errors from `thread/inject_items` are returned through
  the Workflow V2 error boundary without becoming session route logic.

## State Shape

Extend the canonical public state only as much as needed for deterministic UI:

```json
{
  "context": {
    "frameVersion": 3,
    "specVersion": 2,
    "splitManifestVersion": null,
    "stale": true,
    "staleReason": "execution context packet changed.",
    "staleBindings": [
      {
        "role": "execution",
        "threadId": "thread_exec",
        "currentContextPacketHash": "sha256:old",
        "nextContextPacketHash": "sha256:new",
        "currentSourceVersions": {
          "frameVersion": 2,
          "specVersion": 1,
          "splitManifestVersion": null
        },
        "nextSourceVersions": {
          "frameVersion": 3,
          "specVersion": 2,
          "splitManifestVersion": null
        }
      }
    ]
  },
  "allowedActions": ["rebase_context"]
}
```

Internal model options:

- Prefer adding `context_stale_details` or a typed equivalent to
  `NodeWorkflowStateV2` only if details need to persist between reads.
- If stale details can be computed deterministically from current bindings and
  current context packets, compute them at read time and persist only
  `context_stale` / `context_stale_reason`.
- Public wire fields remain camelCase.

## Work Plan

### 1. Add a context freshness service

Create `backend/business/workflow_v2/context_freshness.py` or keep the logic in
`context_builder.py` only if it stays small.

Responsibilities:

- Build the current context packet for every bound role.
- Compare each binding's `sourceVersions` and `contextPacketHash` against the
  current packet.
- Return deterministic stale details sorted by role.
- Mark workflow state stale when details are non-empty.
- Publish `workflow/context_stale` once per state transition into stale, not on
  every read.

This service should not call Session Core. It only detects freshness.

### 2. Make stale detection deterministic

Backend entry points that should check freshness:

- `GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state`
- V4 workflow action routes before normal action authorization
- V2 workflow event adaptation when source artifact events are received
- thread ensure paths before deciding whether a binding is reusable

Rules:

- If a bound role's context changed and the workflow is not terminal, persist
  stale state and expose only `rebase_context`.
- Terminal `done` and `blocked` states keep the current Phase 7 behavior unless
  product decides package review should rebase done-state context. Do not add
  that exception in Phase 8.
- Ask-planning-only nodes should still stale/rebase their ask binding when frame
  or task context changes.

### 3. Add a rebase service method

Add a backend method such as:

`ThreadBindingServiceV2.rebase_context(project_id, node_id, idempotency_key, expected_workflow_version=None, roles=None)`

or split it into `ContextRebaseServiceV2` if that keeps ownership cleaner.

Responsibilities:

- Load current state and freshness details.
- Validate `rebase_context` is allowed.
- Validate optional expected workflow version.
- Validate optional role subset.
- For each affected bound role:
  - build the next role context packet,
  - build a `context_update` packet,
  - append it through Session Core V2 `thread/inject_items`,
  - update the role binding's `sourceVersions`, `contextPacketHash`, and
    `updatedAt`.
- Apply the state-machine `rebase_context` transition with the latest source
  versions.
- Record idempotency with payload hash and full response.
- Publish `workflow/action_completed` for `rebase_context` and
  `workflow/state_changed` after persistence.

Avoid using `ensure_thread(..., force_rebase=True)` as the public rebase action.
The existing force path can stay as a lower-level helper or compatibility path,
but the new endpoint should own all affected roles in one transaction boundary.

### 4. Add the V4 route

Update `backend/routes/workflow_v4.py`:

- Add `ContextRebaseRequest`.
- Add `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`.
- Return `{ rebased, updatedBindings, workflowState }`.
- Reuse existing Workflow V2 and Session Core error response helpers.
- Keep `/v4/session/*` untouched.

### 5. Extend frontend Workflow V2 client and store

Update `frontend/src/features/workflow_v2/api/client.ts`:

- Add `rebaseContextV2`.
- Add response type fields for `rebased` and `updatedBindings`.

Update `workflowStateStoreV2.ts`:

- Add `WorkflowMutationActionV2` value `rebase_context`.
- Add store command `rebaseContext(projectId, nodeId, options?)`.
- Generate `context_rebase:*` idempotency keys in the store.
- Prefer `response.workflowState`; otherwise reload state.

Update `useWorkflowStateV2.ts` to expose `rebaseContext`.

### 6. Add Breadcrumb V2 rebase action

Update `workflowThreadLaneV2.ts`:

- When `allowedActions` contains `rebase_context`, expose a single action on
  the active lane.
- Use a deterministic label such as "Rebase Context".
- Keep normal execution/audit/package actions hidden while stale.

Update `useBreadcrumbConversationControllerV2.tsx`:

- Dispatch `rebaseContext(projectId, nodeId, { expectedWorkflowVersion:
  workflowState.version })`.
- After success, reload/select the current lane thread if it still exists.
- Keep Session V2 pending request overlays owned by `useSessionFacadeV2`.

UI behavior:

- The action strip should show the rebase action where users already expect
  workflow actions.
- The composer remains disabled for business lanes while stale.
- If rebase succeeds and a lane thread remains bound, the existing Session V2
  transcript should show the appended context update packet.

### 7. Tests

Backend unit tests:

- `test_workflow_v2_context_packets.py`
  - packet hash changes when frame/spec/split source versions or payload change,
  - `context_update` references previous and next packet hashes.
- `test_workflow_v2_state_machine.py`
  - stale states expose only `rebase_context`,
  - rebase clears stale context and restores normal allowed actions.
- `test_workflow_v2_thread_binding.py` or new
  `test_workflow_v2_context_rebase.py`
  - detects stale bindings without injecting,
  - rebase injects update packets for all affected bound roles,
  - role subset rebase works,
  - idempotent replay works,
  - same idempotency key with changed payload conflicts.

Backend integration tests:

- Add `backend/tests/integration/test_workflow_v4_phase8.py`.
- Cover:
  - `GET workflow-state` exposes stale details after source version change,
  - normal `execution/start` or `audit/start` returns stale error,
  - `POST context/rebase` updates bindings and clears stale state,
  - rebase publishes V2 events,
  - Session injected items are appended, not replaced.

Frontend tests:

- `workflowStateStoreV2.test.ts`
  - `rebaseContext` calls the V4 route and stores returned state,
  - errors are surfaced and active mutation clears.
- `workflowThreadLaneV2.test.ts`
  - stale state produces only the rebase action.
- `BreadcrumbChatViewV2.workflow-v2.integration.test.tsx`
  - stale state renders rebase action,
  - click calls `rebaseContext` with expected workflow version,
  - normal action buttons are hidden while stale.
- `workflowEventBridgeV2.test.tsx`
  - `workflow/context_stale` refreshes state.

### 8. Add Phase 8 guard script

Add `scripts/check_workflow_v2_phase8.py`:

- Assert `backend/routes/workflow_v4.py` exposes `/context/rebase`.
- Assert Workflow V2 frontend client/store/hook expose `rebaseContext`.
- Assert `workflowThreadLaneV2` derives `rebase_context`.
- Assert `/v4/session/*` route code remains workflow-business-free.
- Assert no Breadcrumb V2 path calls V3 workflow state or mutation endpoints.
- Assert tests or fixtures cover stale details, rebase route, and
  `thread/inject_items` append behavior.

## Acceptance Gates

Grep gates:

```powershell
rg -n "context/rebase|rebaseContext|rebase_context" backend/routes/workflow_v4.py backend/business/workflow_v2 frontend/src/features/workflow_v2 frontend/src/features/conversation
rg -n "useWorkflowStateStoreV3|useWorkflowEventBridgeV3|resolveWorkflowProjection" frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
rg -n "/v3/projects/.*/workflow" frontend/src/features/workflow_v2 frontend/src/features/conversation/useBreadcrumbConversationControllerV2.tsx
```

Expected result:

- First command shows the V4 route, backend service/state-machine path, and
  frontend client/store/controller path.
- Second and third commands have no matches in the Breadcrumb V2 active path.

Focused tests:

```powershell
python -m pytest backend/tests/unit/test_workflow_v2_state_machine.py backend/tests/unit/test_workflow_v2_context_packets.py backend/tests/unit/test_workflow_v2_thread_binding.py backend/tests/unit/test_workflow_v2_context_rebase.py backend/tests/integration/test_workflow_v4_phase8.py
Push-Location frontend; npx vitest run tests/unit/workflowStateStoreV2.test.ts tests/unit/workflowEventBridgeV2.test.tsx tests/unit/workflowThreadLaneV2.test.ts tests/unit/BreadcrumbChatViewV2.workflow-v2.integration.test.tsx; Pop-Location
python scripts/check_workflow_v2_phase6.py
python scripts/check_workflow_v2_phase7.py
python scripts/check_workflow_v2_phase8.py
```

Smoke checks:

- Start with a node that has an execution thread binding.
- Change or simulate a changed confirmed frame/spec source version.
- Open Breadcrumb V2 and confirm workflow state shows stale context.
- Confirm normal execution/audit/package actions are hidden and only "Rebase
  Context" is available.
- Rebase context.
- Confirm the same Session V2 thread contains an appended context update item.
- Confirm `workflowState.context.stale` is `false` and normal allowed actions
  return.
- Confirm `/v4/session/*` traffic remains session-only.

## Rollback

- Keep existing `ensure_thread(..., force_rebase=True)` behavior as lower-level
  fallback.
- If the dedicated rebase route has a runtime blocker, hide
  `rebase_context` in the frontend while keeping stale blocking in the backend.
- Do not delete existing context packets or thread bindings.
- Do not rewrite legacy workflow files during rollback.
- Keep V3 compatibility routes available.

## Done Criteria

- Workflow V2 state exposes deterministic stale context details.
- Normal business actions are blocked while non-terminal context is stale.
- `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase` appends context
  updates to all affected bound Session V2 threads and clears stale state.
- Breadcrumb V2 exposes a deterministic rebase action and dispatches only V4
  Workflow V2 routes.
- Workflow V2 events refresh the UI on stale detection and rebase completion.
- `/v4/session/*` remains session-only.
- Phase 6, Phase 7, and Phase 8 guard scripts pass.
