# Workflow V2 Roadmap

This roadmap turns the current hybrid stack into a Workflow Core V2 stack while
keeping the product runnable at every gate.

## Goal

Move execution/audit business ownership out of the V3 workflow service and into
`backend/business/workflow_v2`, then cut the Breadcrumb V2 UI over to V4
workflow routes while continuing to use Session Core V2 for all conversation
runtime behavior.

## Non-goals

- Do not replace `/v4/session/*`; it remains the session runtime API.
- Do not migrate all project, node-detail, or artifact APIs just to unblock the
  workflow cutover.
- Do not delete V3 routes until they are compatibility adapters over Workflow
  Core V2 and the new UI path no longer imports V3 workflow modules.

## Phase 0 - Contract Alignment and Guardrails

Deliverables:

- Freeze the target V4 workflow route family:
  `/v4/projects/{projectId}/nodes/{nodeId}/...`.
- Freeze the V2 workflow state envelope, workflow event envelope, idempotency
  rules, and error codes.
- Freeze public/internal naming:
  - Public V4 workflow responses use camelCase and `phase`/`version`.
  - Internal Python models use snake_case and `state_version`.
  - Legacy V3 compatibility views may continue returning `workflowPhase` and
    legacy thread id field names.
- Freeze the V3-to-V2 phase mapping used by read-through converters:
  - `idle` -> `ready_for_execution`
  - `execution_running` -> `executing`
  - `execution_decision_pending` -> `execution_completed`
  - `audit_running` -> `audit_running`
  - `audit_decision_pending` -> `review_pending`
  - `done` -> `done`
  - `failed` -> `blocked`
- Freeze action semantics:
  - Existing V3 `improve-in-execution` maps to V4
    `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve`.
  - V4 `audit/request-changes` is a separate audit decision action and is not
    the direct replacement for the current Breadcrumb improve button.
- Add or update docs in this directory when contract changes are needed.
- Identify repo path corrections before implementation:
  - Session manager is `backend/session_core_v2/connection/manager.py`.
  - Session protocol client is `backend/session_core_v2/protocol/client.py`.
  - Existing `WorkflowStateStore` folder name is `workflow_v2`, but the payload
    is still legacy-shaped and must not be treated as canonical V2 by default.

Done when:

- API, event, state, and storage ownership are documented.
- The implementation team agrees that `/v4/session/*` remains session-only.
- `thread/inject_items` is marked as a prerequisite for thread binding.
- `docs/migration/phase-0-gate-report-v1.md` records the current hybrid audit
  and Phase 0 decisions.
- `python scripts/check_workflow_v2_phase0.py` passes.

## Phase 1 - Workflow Core V2 Skeleton

Create:

```text
backend/business/workflow_v2/
  __init__.py
  models.py
  state_machine.py
  repository.py
  thread_binding.py
  context_packets.py
  context_builder.py
  artifact_orchestrator.py
  execution_audit_orchestrator.py
  events.py
  errors.py
```

Responsibilities:

- `models.py`: canonical Pydantic models for workflow state, bindings,
  decisions, context metadata, actions, and events.
- `state_machine.py`: pure transition logic with no storage, Codex, session,
  route, or SSE dependencies.
- `repository.py`: read/write canonical V2 state and optional migration
  converters from the existing workflow store shape.
- `events.py`: canonical workflow event objects.
- `errors.py`: deterministic domain errors and route error mapping.

Done when:

- Pure unit tests cover allowed actions and phase transitions.
- State models carry `schema_version`, `state_version`, timestamps, and enough
  fields to preserve idempotency and async run ids.
- No UI or V3 behavior has changed.

## Phase 2 - Session Core Prerequisites

Implement the Session Core capabilities that Workflow Core V2 needs:

- Add protocol support for `thread/inject_items` in
  `backend/session_core_v2/protocol/client.py`.
- Add manager support in `backend/session_core_v2/connection/manager.py`.
- Replace the current `/v4/session/threads/{threadId}/inject-items` stub with a
  real implementation or expose an internal manager method used by workflow V2.
- Add idempotency for inject operations.
- Confirm existing `turn/start` `outputSchema` support is sufficient for audit
  runs.
- Add `review/start` protocol support only if the V2 audit path chooses that
  app-server method instead of `turn/start` with `outputSchema`.

Done when:

- Backend tests prove context items can be appended to a thread without starting
  a user turn.
- Injected context appears in thread read/turn history or in the canonical event
  stream according to the Session Core V2 contract.
- Session routes still contain no workflow-specific business branching.

## Phase 3 - Thread Binding and Context Packets

Build `ThreadBindingServiceV2` and the context packet system.

Thread roles:

- `ask_planning`
- `execution`
- `audit`
- `package_review`

Binding rules:

- Backend owns create/reuse/rebase decisions.
- Frontend never decides whether to call `thread/start`, fork, or reuse.
- `ask_planning` gets ask or child-activation context.
- `execution` gets execution context and does not fork ask by default.
- `audit` gets audit context and can run through `review/start` or
  `turn/start` with `outputSchema`.
- `package_review` gets parent plus child rollup context.

Done when:

- `ensure_thread` is implemented behind a backend API and stores binding
  metadata with source artifact versions and context packet hashes.
- Context packets are canonical JSON models even if initial delivery is a
  model-visible neutral context message.
- Unit tests cover reuse, force rebase, and stale source version handling.

## Phase 4 - V4 Workflow Read Surface and Events

Add:

- `backend/routes/workflow_v4.py`
- `GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state`
- `GET /v4/projects/{projectId}/events`
- V2 workflow event publisher or adapter.

Frontend can add in parallel:

```text
frontend/src/features/workflow_v2/
  api/client.ts
  hooks/useWorkflowStateV2.ts
  hooks/useWorkflowEventBridgeV2.ts
  store/workflowStateStoreV2.ts
  types.ts
```

Done when:

- V4 read state returns the canonical V2 envelope.
- Workflow events are separate from Session Core V2 item/turn events.
- The existing UI path still runs unchanged.

## Phase 5 - Shared Execution/Audit Orchestrator

Move business logic out of `ExecutionAuditWorkflowService` into
`ExecutionAuditOrchestratorV2` incrementally.

Target methods:

- `start_execution`
- `complete_execution`
- `mark_done_from_execution`
- `start_audit`
- `accept_audit`
- `request_improvements`
- `start_package_review`

Adapter rule:

- V3 route -> legacy `ExecutionAuditWorkflowService` -> V2 orchestrator ->
  V2 workflow state.
- The legacy service converts V2 responses back to the old V3 shape until the
  old UI path is retired.

Suggested migration order:

1. Read state converter and allowed action parity.
2. `mark_done_from_execution`.
3. `start_audit`.
4. `request_improvements`.
5. `accept_audit`.
6. `start_execution`.
7. `package_review`.

Done when:

- Each migrated mutation has a V4 endpoint and a V3 compatibility path calling
  the same V2 orchestrator code.
- Existing V3 endpoint tests still pass or are updated to assert adapter
  behavior.
- The business source of truth for migrated mutations is V2.

## Phase 6 - Breadcrumb V2 Frontend Cutover

Status: complete.

Detailed plan:

- `docs/migration/phase-6-breadcrumb-v2-cutover-plan-v1.md`

Rewrite `useBreadcrumbConversationControllerV2` to use:

- `useSessionFacadeV2`
- `useWorkflowStateV2`
- `useWorkflowEventBridgeV2`
- `frontend/src/features/workflow_v2/api/client.ts`

Remove from the new Breadcrumb path:

- `useWorkflowStateStoreV3`
- `useWorkflowEventBridgeV3`
- `resolveWorkflowProjection`
- V3 workflow mutation imports.

Done when:

- Breadcrumb V2 uses V2 workflow state for active role/thread selection.
- Workflow action strip receives V2 actions and dispatches V4 workflow
  mutations.
- Session transcript, composer, model selection, pending request overlays, and
  interrupt behavior still come from Session Core V2 components/facade.
- `python scripts/check_workflow_v2_phase6.py` passes.

## Phase 7 - End-to-End Workflow Actions

Status: complete.

Detailed plan:

- `docs/migration/phase-7-end-to-end-workflow-actions-plan-v1.md`

Complete and verify action flows:

- Ensure ask planning thread.
- Start execution.
- Complete execution from Session V2 turn completion.
- Mark done from execution.
- Start audit.
- Complete audit from Session V2 review/audit completion.
- Request changes / improve in execution.
- Accept audit / mark done.
- Start package review.

Done when:

- New UI path does not call V3 workflow state or mutation endpoints.
- Execution and audit transcripts render through Session Core V2 events.
- Workflow state changes arrive through the V2 workflow event bridge.
- Package review has a V4 start route and verified Workflow V2 thread binding.
- `python scripts/check_workflow_v2_phase7.py` passes.

## Phase 8 - Context Stale and Rebase

Status: complete.

Detailed plan:

- `docs/migration/phase-8-context-stale-rebase-plan-v1.md`

Implement context stale detection and rebase:

- Pin source artifact versions in thread bindings and context packet metadata.
- Mark context stale when frame/spec/split versions change.
- Add `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`.
- Append context update packets instead of mutating historical context.

Done when:

- V2 workflow state exposes stale context details and `rebase_context`.
- Rebase injects context updates into affected threads and clears stale state.
- UI exposes a deterministic rebase action.
- `python scripts/check_workflow_v2_phase8.py` passes.

## Phase 9 - Artifact Orchestrator Alignment

Status: complete.

Detailed plan:

- `docs/migration/phase-9-artifact-orchestrator-alignment-plan-v1.md`

Move frame/spec/clarify/split workflow decisions behind
`artifact_orchestrator.py` without forcing them into regular session chat.

Done when:

- Artifact jobs write versioned artifacts.
- Confirmed artifact summaries can be injected into active threads when useful.
- Artifact confirmation updates Workflow V2 state and publishes V2 workflow
  events.
- `python scripts/check_workflow_v2_phase9.py` passes.

## Phase 10 - V3 Compatibility, Deprecation, and Removal

Convert V3 workflow routes into compatibility adapters:

- `/v3/projects/.../workflow-state` reads V2 state and returns the old V3 view.
- `/v3/projects/.../workflow/*` calls V2 orchestrator methods and converts
  responses.

Done when:

- New UI path is V2-only for workflow state, events, and mutations.
- Legacy V3 tests cover adapter compatibility.
- V3 workflow routes can be marked deprecated or kept read-only.
- V3-only workflow business logic is removed after telemetry and tests confirm
  no active dependency.
