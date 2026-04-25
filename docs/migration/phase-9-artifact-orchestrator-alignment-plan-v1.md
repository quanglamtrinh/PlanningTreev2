# Workflow V2 Phase 9 Artifact Orchestrator Alignment Plan v1

Phase 9 moves frame/spec/clarify/split workflow decisions behind Workflow Core
V2 without turning artifact generation into regular session chat. Phase 8 made
long-lived Workflow V2 threads freshness-aware; Phase 9 makes artifact changes
the canonical source of those freshness transitions.

Status: complete.

## Starting Point

Assumptions:

- Phase 8 is complete.
- Breadcrumb V2 workflow actions use Workflow V2 and Session Core V2.
- Workflow V2 already owns execution/audit orchestration, thread binding,
  context packet freshness, context rebase, and workflow events.
- `backend/business/workflow_v2/artifact_orchestrator.py` exists but is still a
  stub.

Current artifact ownership:

- V3-ish node routes in `backend/routes/nodes.py` own frame/spec/clarify reads,
  generation starts, status reads, and confirmations.
- `backend/routes/split.py` owns split start/status.
- `NodeDetailService` owns frame confirmation, clarify seed/update/apply, spec
  confirmation, and detail-state derivation.
- `FrameGenerationService`, `ClarifyGenerationService`, `SpecGenerationService`,
  and `SplitService` own asynchronous artifact jobs and sidecar job state.
- Frontend artifact flows still call `/v3/...` from `frontend/src/api/client.ts`
  through `detail-state-store`, `clarify-store`, `project-store`,
  `NodeDocumentEditor`, `ClarifyPanel`, and `SplitPanel`.
- `WorkflowContextBuilderV2` reads confirmed frame/spec metadata for context
  packet source versions; `splitManifestVersion` is still `null`.

Remaining gaps:

- Artifact workflow decisions are not routed through Workflow Core V2.
- Artifact confirmations do not deterministically sync Workflow V2 source
  version fields or publish native Workflow V2 events.
- Artifact changes can make thread context stale, but the transition is mostly
  observed on later Workflow V2 reads/rebase checks instead of being owned by
  the artifact action that caused it.
- Artifact job status is split across legacy sidecar files and legacy response
  shapes.
- The new UI path still depends on V3 artifact mutation endpoints.

## Goal

Make `ArtifactOrchestratorV2` the backend owner for artifact workflow decisions:

- Start and observe frame, clarify, spec, and split jobs through a Workflow V2
  orchestrator.
- Confirm frame/clarify/spec through Workflow V2.
- Update canonical Workflow V2 source versions when confirmed artifacts change.
- Publish native Workflow V2 artifact/state events after artifact starts,
  completions, confirmations, failures, and split materialization.
- Mark or refresh context stale through the Phase 8 freshness path when artifact
  versions change.
- Expose a V4 artifact route family for frontend mutation/status paths.
- Keep generation jobs as artifact workflows, not Session Core V2 chat turns.

## Non-goals

- Do not move artifact generation into `/v4/session/*`.
- Do not replace the existing frame/spec/clarify/split generation internals in
  one step; existing services can remain lower-level workers during Phase 9.
- Do not delete V3 routes. Phase 10 owns compatibility/deprecation/removal.
- Do not auto-rebase active threads after artifact confirmation. Confirmation
  may make context stale; the user-visible rebase action from Phase 8 remains
  the repair path.
- Do not migrate general document read/write APIs unless needed for artifact
  workflow correctness.
- Do not change Session Core V2 event streams to carry workflow artifact events.

## Ownership Contract

`ArtifactOrchestratorV2` becomes the only business entry point for artifact
workflow decisions on the V2 path.

Initial dependencies may include:

- `WorkflowStateRepositoryV2`
- `WorkflowEventPublisherV2`
- `ThreadBindingServiceV2`
- `WorkflowContextBuilderV2` or a small source-version helper
- `NodeDetailService`
- `FrameGenerationService`
- `ClarifyGenerationService`
- `SpecGenerationService`
- `SplitService`
- `Storage` / `TreeService` where needed for version reads

Existing artifact services should become worker/adapters from the V2
perspective. They may still own low-level IO, prompt execution, sidecar job
files, and materialization while the orchestrator owns:

- action authorization and idempotency,
- canonical response shape,
- Workflow V2 state synchronization,
- Workflow V2 event publication,
- context freshness refresh after artifact changes.

## Public API Contract

Add a V4 artifact route family under the existing Workflow V2 project/node
namespace:

```text
GET  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/state
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/generate
GET  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/generation-status
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/frame/confirm
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/generate
GET  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify
PUT  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify
GET  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/generation-status
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/clarify/confirm
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/generate
GET  /v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/generation-status
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/spec/confirm
POST /v4/projects/{projectId}/nodes/{nodeId}/artifacts/split/start
GET  /v4/projects/{projectId}/artifact-jobs/split/status
```

All mutating endpoints accept:

```json
{
  "idempotencyKey": "artifact-action:uuid"
}
```

`PUT clarify` accepts the existing answer payload plus an optional
`idempotencyKey`.

`split/start` accepts:

```json
{
  "idempotencyKey": "split-start:uuid",
  "mode": "workflow"
}
```

Mutation responses should include:

```json
{
  "accepted": true,
  "job": {
    "jobId": "fgen_123",
    "kind": "frame",
    "status": "running",
    "nodeId": "node_1"
  },
  "artifactState": { "...": "canonical artifact state" },
  "workflowState": { "...": "canonical Workflow V2 state when changed" }
}
```

Confirmation responses should include:

```json
{
  "confirmed": true,
  "artifact": {
    "kind": "frame",
    "frameVersion": 3,
    "confirmedAt": "2026-04-24T00:00:00Z"
  },
  "artifactState": { "...": "canonical artifact state" },
  "workflowState": { "...": "canonical Workflow V2 state" }
}
```

Error rules:

- Existing domain validation errors may initially keep their current codes when
  surfaced through V4.
- Workflow-owned idempotency conflicts use `ERR_WORKFLOW_IDEMPOTENCY_CONFLICT`.
- Version mismatches use deterministic Workflow V2 conflict errors.
- Session Core errors must not appear unless the optional artifact summary
  injection path calls `thread/inject_items`.

## Artifact State Shape

Add a canonical V4 artifact state response that can be adapted from existing
detail-state and job sidecars:

```json
{
  "schemaVersion": 1,
  "projectId": "p1",
  "nodeId": "n1",
  "versions": {
    "frameVersion": 3,
    "confirmedFrameVersion": 3,
    "specVersion": 3,
    "splitManifestVersion": null
  },
  "artifacts": {
    "frame": {
      "confirmed": true,
      "confirmedAt": "2026-04-24T00:00:00Z",
      "needsReconfirm": false
    },
    "clarify": {
      "confirmed": true,
      "sourceFrameVersion": 3,
      "openQuestions": 0
    },
    "spec": {
      "confirmed": true,
      "sourceFrameVersion": 3,
      "stale": false
    },
    "split": {
      "status": "idle",
      "mode": null,
      "jobId": null
    }
  },
  "jobs": {
    "frame": { "status": "idle", "jobId": null, "lastError": null },
    "clarify": { "status": "idle", "jobId": null, "lastError": null },
    "spec": { "status": "idle", "jobId": null, "lastError": null },
    "split": { "status": "idle", "jobId": null, "lastError": null }
  }
}
```

The response can include legacy detail-state fields during transition only if
the frontend still needs them. Public V4 names should be camelCase.

## Workflow State Synchronization

Phase 9 should define and implement one source-version sync helper:

`sync_artifact_source_versions(project_id, node_id, reason) -> NodeWorkflowStateV2`

Rules:

- Read current confirmed frame/spec metadata and split manifest metadata.
- Update `NodeWorkflowStateV2.frame_version`, `spec_version`, and
  `split_manifest_version` to the current source versions.
- Preserve phase, decisions, run ids, and thread bindings.
- Publish `workflow/state_changed` when the version fields change.
- Call `ThreadBindingServiceV2.refresh_context_freshness(...)` after version
  changes so active bindings become explicitly stale when their packets no
  longer match.
- Do not clear stale state unless the Phase 8 rebase route updates the relevant
  bindings.

`splitManifestVersion` should move from permanently `null` to a deterministic
value if split materialization already writes a stable manifest or split state
revision. If no stable revision exists yet, Phase 9 should add one near split
materialization rather than deriving it from wall-clock-only state.

## Workflow Event Contract

Extend native Workflow V2 events for artifact workflows:

- `workflow/artifact_job_started`
- `workflow/artifact_job_completed`
- `workflow/artifact_job_failed`
- `workflow/artifact_confirmed`
- `workflow/artifact_state_changed`

Each event should include:

```json
{
  "type": "workflow/artifact_confirmed",
  "projectId": "p1",
  "nodeId": "n1",
  "version": 13,
  "details": {
    "artifact": "frame",
    "frameVersion": 3,
    "reason": "frame_confirmed"
  }
}
```

`workflow/state_changed` remains the canonical signal for Workflow V2 state
changes. Artifact-specific events are descriptive and should not replace state
refresh.

The V4 workflow event bridge should refresh:

- artifact state after artifact events,
- workflow state after state/context events,
- project snapshot after split completion.

## Artifact Summary Injection

Confirmed artifact summaries may be injected into active threads, but this is
supplemental:

- Injection is backend-owned and optional per action.
- Injection uses Session Core V2 `thread/inject_items`; no `/v4/session/*`
  route gains artifact branching.
- Injected items should use metadata such as:
  - `workflowArtifact: true`
  - `artifactKind`
  - `artifactVersion`
  - `packetKind: "artifact_summary"`
- Summary injection never clears stale context and never replaces context
  rebase.
- If context is stale, prefer marking stale and letting the Phase 8 rebase path
  append the full updated context packet.

## Work Plan

### 1. Freeze the current artifact boundary

Document the current route/service ownership in code comments or tests:

- `nodes.py` currently calls `NodeDetailService` and generation services
  directly.
- `split.py` currently calls `SplitService` directly.
- Frontend artifact calls originate from `frontend/src/api/client.ts`.
- `ArtifactOrchestratorV2` is currently unused/stubbed.

This keeps Phase 9 focused on ownership and adapters, not a surprise rewrite of
artifact generation internals.

### 2. Implement `ArtifactOrchestratorV2` as a facade first

Replace the stub with methods such as:

- `get_artifact_state(project_id, node_id)`
- `start_frame_generation(project_id, node_id, idempotency_key)`
- `get_frame_generation_status(project_id, node_id)`
- `confirm_frame(project_id, node_id, idempotency_key)`
- `start_clarify_generation(project_id, node_id, idempotency_key)`
- `get_clarify(project_id, node_id)`
- `update_clarify(project_id, node_id, answers, idempotency_key=None)`
- `confirm_clarify(project_id, node_id, idempotency_key)`
- `start_spec_generation(project_id, node_id, idempotency_key)`
- `get_spec_generation_status(project_id, node_id)`
- `confirm_spec(project_id, node_id, idempotency_key)`
- `start_split(project_id, node_id, mode, idempotency_key)`
- `get_split_status(project_id)`

The first implementation may delegate to existing services. The important
change is that all V4 decisions pass through one V2 owner.

### 3. Add source-version state sync

After these actions, sync Workflow V2 source versions and refresh context
freshness:

- frame confirmation,
- clarify confirmation when it patches frame content,
- spec generation when it resets spec confirmation,
- spec confirmation,
- split materialization/completion,
- direct frame document save if it invalidates confirmed frame/spec freshness.

Clarify answer edits that do not change confirmed frame/spec versions should
not mark context stale by themselves.

### 4. Add V4 artifact routes

Create `backend/routes/artifacts_v4.py` or a small route module adjacent to
`workflow_v4.py`.

Rules:

- Reuse Workflow V2 error response helpers where possible.
- Keep response envelopes direct and canonical; do not wrap successful V4
  responses in legacy `{ ok, data }`.
- Keep Session Core V2 routes untouched.
- Register the route module in `backend/main.py`.
- Store the orchestrator at `app.state.artifact_orchestrator_v2`.

### 5. Add native artifact events

Publish native Workflow V2 events from the orchestrator for:

- job accepted/started,
- job completion,
- job failure,
- artifact confirmation,
- split materialization.

If existing background worker services complete asynchronously, Phase 9 can
start with polling/status-triggered event publication, but the target is for
worker completion to call back into the orchestrator or a small completion
observer so events are not only emitted on the next poll.

### 6. Cut frontend artifact mutations to V4

Add a frontend V2 artifact client/store, for example:

```text
frontend/src/features/workflow_v2/api/artifactClient.ts
frontend/src/features/workflow_v2/store/artifactStateStoreV2.ts
frontend/src/features/workflow_v2/hooks/useArtifactStateV2.ts
```

Then migrate active artifact mutation/status call sites:

- `NodeDocumentEditor` frame/spec generate and confirm.
- `ClarifyPanel` clarify generate/confirm.
- `clarify-store` clarify update/confirm calls.
- `project-store` split start/status.
- any create-task auto-frame-generation path.

Document read/write endpoints can remain on existing APIs until a later phase if
they are plain document storage and not workflow decisions.

### 7. Wire artifact events into frontend refresh

Update `useWorkflowEventBridgeV2` or add a companion artifact bridge so:

- artifact events refresh artifact state,
- state/context events refresh Workflow V2 state,
- split completion refreshes project snapshot,
- stale context events still show the Phase 8 rebase action.

### 8. Add tests

Backend unit tests:

- `test_workflow_v2_artifact_orchestrator.py`
  - delegates generation to worker services,
  - confirms frame/spec through V2,
  - records idempotency and conflicts,
  - syncs Workflow V2 source versions,
  - refreshes context stale after confirmed artifact changes,
  - publishes native Workflow V2 artifact/state events.

Backend integration tests:

- `test_workflow_v4_phase9.py`
  - V4 frame generate/status/confirm route uses the orchestrator,
  - V4 clarify update/confirm route uses the orchestrator,
  - V4 spec generate/status/confirm route uses the orchestrator,
  - V4 split start/status route uses the orchestrator,
  - artifact confirmation makes existing thread bindings stale,
  - split completion updates snapshot and split source version,
  - `/v4/session/*` remains artifact-business-free.

Frontend tests:

- `artifactStateStoreV2.test.ts`
  - calls V4 artifact routes,
  - stores artifact state,
  - clears active mutations/status flags.
- `NodeDocumentEditor` tests
  - generate/confirm frame/spec use V4 artifact client.
- `ClarifyPanel` / `clarify-store` tests
  - clarify generate/update/confirm use V4 artifact client.
- `project-store` split tests
  - split start/status uses V4 artifact route and refreshes snapshot on
    completion.
- `workflowEventBridgeV2` tests
  - artifact events refresh artifact state and Workflow V2 state as needed.

### 9. Add Phase 9 guard script

Add `scripts/check_workflow_v2_phase9.py`:

- Assert `ArtifactOrchestratorV2` no longer only raises
  `WorkflowV2NotImplementedError`.
- Assert V4 artifact routes are registered.
- Assert active frontend artifact mutation/status paths no longer call
  `/v3/.../generate-frame`, `/confirm-frame`, `/generate-clarify`,
  `/confirm-clarify`, `/generate-spec`, `/confirm-spec`, or `/split`.
- Assert `/v4/session/*` route code has no artifact workflow branching.
- Assert Phase 8 rebase route and guards still exist.
- Assert tests mention artifact events, source-version sync, and stale context
  refresh.

## Acceptance Gates

Grep gates:

```powershell
rg -n "ArtifactOrchestratorV2|artifacts/.*/(generate|confirm)|artifact_job|artifact_confirmed" backend
rg -n "/v3/projects/.*/(generate-frame|confirm-frame|generate-clarify|confirm-clarify|generate-spec|confirm-spec|split)" frontend/src
rg -n "artifact_orchestrator|workflowArtifact|artifact_summary" backend/business backend/routes frontend/src
```

Expected result:

- First command shows the V2 orchestrator, V4 routes, event publishing, and
  tests.
- Second command has no matches in active frontend mutation/status paths after
  cutover. Plain document reads/writes can remain if explicitly documented.
- Third command shows backend-owned optional artifact summary injection only
  outside `/v4/session/*`.

Focused tests:

```powershell
python -m pytest backend/tests/unit/test_workflow_v2_artifact_orchestrator.py backend/tests/integration/test_workflow_v4_phase9.py
Push-Location frontend; npx vitest run tests/unit/artifactStateStoreV2.test.ts tests/unit/workflowEventBridgeV2.test.tsx; Pop-Location
python scripts/check_workflow_v2_phase6.py
python scripts/check_workflow_v2_phase7.py
python scripts/check_workflow_v2_phase8.py
python scripts/check_workflow_v2_phase9.py
```

Regression tests:

```powershell
python -m pytest backend/tests/unit/test_frame_generation_service.py backend/tests/unit/test_clarify_generation_service.py backend/tests/unit/test_spec_generation_service.py backend/tests/unit/test_split_service.py
python -m pytest backend/tests/integration/test_node_documents_api.py backend/tests/integration/test_split_api.py
```

Smoke checks:

- Create a task and confirm the new node can still auto-start frame generation.
- Generate and confirm frame through V4.
- Confirm that Workflow V2 state source versions update.
- Ensure an ask/execution thread binding, then confirm a changed artifact and
  verify `context.stale` plus `rebase_context`.
- Rebase context and verify the active thread receives an appended update.
- Generate clarify, answer questions, confirm clarify, and verify frame
  reconfirm behavior remains intact.
- Generate and confirm spec through V4.
- Start split through V4 and verify snapshot/project state refresh after
  completion.
- Confirm `/v4/session/*` traffic remains session-only.

## Rollback

- Keep V3 artifact routes available during Phase 9.
- If a V4 artifact route has a blocker, temporarily route only that frontend
  action back to the existing V3 endpoint while leaving the orchestrator in
  place for other actions.
- Do not delete existing generation sidecar files or split state files.
- Do not rewrite Session V2 thread history.
- Do not auto-clear stale context; leave the Phase 8 rebase action as the
  repair path.

## Done Criteria

- `ArtifactOrchestratorV2` owns frame/spec/clarify/split decisions for V4.
- V4 artifact routes exist and are used by the active frontend artifact
  mutation/status paths.
- Artifact confirmations update Workflow V2 source versions and publish native
  Workflow V2 events.
- Artifact version changes refresh context freshness and expose stale bindings
  when active threads need rebase.
- Split materialization has a deterministic source version or documented
  `null` fallback with tests.
- Optional artifact summary injection, if implemented, appends Session V2 items
  without replacing context rebase.
- `/v4/session/*` remains session-only.
- Phase 6, Phase 7, Phase 8, and Phase 9 guard scripts pass.
