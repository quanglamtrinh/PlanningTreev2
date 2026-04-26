# Workflow V2 Cutover Checklist

Use this checklist to keep the migration incremental and reversible.

## Backend Gates

Phase 0 contract gate:

- `docs/migration/phase-0-gate-report-v1.md` exists.
- `python scripts/check_workflow_v2_phase0.py` passes.
- Public V4 workflow wire naming, V3-to-V2 phase mapping, route ownership, and
  `thread/inject_items` prerequisite are documented.
- No runtime, route, or frontend behavior changes are required for Phase 0.

Phase 1 skeleton:

- `backend/business/workflow_v2/models.py` exists.
- `backend/business/workflow_v2/state_machine.py` has pure unit tests.
- `backend/business/workflow_v2/repository.py` owns canonical V2 state
  read/write and legacy conversion.
- `allowed_actions` are derived from state, not hand-maintained in storage.

Session prerequisite gate:

- `backend/session_core_v2/protocol/client.py` exposes `thread/inject_items`.
- `backend/session_core_v2/connection/manager.py` forwards Codex-compatible
  inject payloads without thread-runtime idempotency.
- `/v4/session/threads/{threadId}/inject-items` is implemented or an equivalent
  internal method exists for Workflow V2.
- Session Core V2 route code remains workflow-business-free.

Workflow V4 route gate:

- `backend/routes/workflow_v4.py` exists.
- `backend/main.py` includes the V4 workflow router without a `/v3` prefix.
- `GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state` returns V2 state.
- `GET /v4/projects/{projectId}/events` streams workflow events only.
- Mutating endpoints require idempotency keys.

Orchestrator gate:

- V2 orchestrator owns one migrated mutation at a time.
- V3 compatibility adapter calls the same V2 orchestrator path.
- Existing V3 integration tests pass through the adapter or are intentionally
  updated with compatibility assertions.

## Frontend Gates

Parallel V2 store/client gate:

- `frontend/src/features/workflow_v2/api/client.ts` exists.
- `frontend/src/features/workflow_v2/store/workflowStateStoreV2.ts` exists.
- `frontend/src/features/workflow_v2/hooks/useWorkflowStateV2.ts` exists.
- `frontend/src/features/workflow_v2/hooks/useWorkflowEventBridgeV2.ts` exists.
- `frontend/src/features/workflow_v2/types.ts` defines V2 state/actions.

Breadcrumb cutover gate:

- `useBreadcrumbConversationControllerV2` imports Workflow V2 hooks/client.
- It still imports `useSessionFacadeV2` for session runtime state and commands.
- It does not import V3 workflow store, event bridge, projection, or mutations.
- Workflow action strip receives V2 actions.
- Thread selection is based on V2 role bindings.

## Grep Gates

These gates are scoped to the new Breadcrumb workflow path. Project snapshot and
node-detail APIs may still use `/v3` until they have their own migration plan.

PowerShell examples:

```powershell
rg -n "useWorkflowStateStoreV3" frontend/src/features/conversation
rg -n "useWorkflowEventBridgeV3" frontend/src/features/conversation
rg -n "resolveWorkflowProjection" frontend/src/features/conversation
rg -n "reviewInAudit|markDoneFromExecution|improveInExecution|markDoneFromAudit" frontend/src/features/conversation
rg -n "/v3/projects/.*/workflow" frontend/src
```

Done criteria:

- No matches in the new Breadcrumb V2 path.
- Any remaining matches are legacy-only, test-only, or explicitly documented.

## Test Gates

Backend:

- Unit tests for V2 state transitions and allowed actions.
- Unit tests for context packet hashes and stale detection.
- Unit tests for thread binding reuse, create, force rebase, and source version
  changes.
- Integration tests for V4 workflow state, ensure thread, and each migrated
  mutation.
- Adapter tests proving V3 routes call V2 orchestrator behavior.
- Session Core V2 tests for Codex-compatible `thread/inject_items` payloads.

Frontend:

- Unit tests for Workflow V2 store load/mutation behavior.
- Unit tests for Workflow V2 event bridge refresh behavior.
- Breadcrumb tests showing V2 workflow state selects the correct Session V2
  thread.
- Breadcrumb tests for action dispatch and pending request overlays.

Smoke:

- Open a node and ensure ask planning thread.
- Submit user text through Session V2 composer.
- Start execution.
- Render execution transcript from Session Core V2.
- Mark done from execution.
- Start audit.
- Request improvements.
- Accept audit and complete node.

## Rollback Guidance

Keep rollback config-only where possible:

- Leave V3 workflow routes available throughout migration.
- Gate Breadcrumb Workflow V2 cutover behind a feature flag if the app already
  has a suitable flag system.
- Keep V3 compatibility adapter returning the legacy view shape until the new UI
  path is stable.
- Do not destructively rewrite legacy workflow state files in early phases.
  Prefer read-through conversion into canonical V2 models.

## Risk Register

Risk: `thread/inject_items` is not production-ready.

Mitigation: implement and test it before thread binding/context packet work.
Keep a neutral context-message fallback only as a delivery format, not as the
canonical packet model.

Risk: V2 state duplicates V3 state and drifts.

Mitigation: introduce a repository/converter boundary and migrate one mutation
at a time. Do not allow V3 and V2 services to mutate the same business fields
independently.

Risk: `allowed_actions` becomes stale.

Mitigation: compute actions from the pure state machine at read time.

Risk: route prefix confusion.

Mitigation: workflow business routes use `/v4/projects/...`; session runtime
routes remain `/v4/session/*`.

Risk: frontend still depends on V3 event refresh.

Mitigation: cut over `useWorkflowEventBridgeV2` before removing V3 mutations
from the controller.

Risk: async/sync mismatch.

Mitigation: keep V2 orchestrator synchronous at first, matching existing storage
and service style. Introduce async only when underlying dependencies are async.

Risk: package review scope expands before core execution/audit stabilizes.

Mitigation: keep package review behind the later phase gate and avoid blocking
the primary Breadcrumb migration on it.
