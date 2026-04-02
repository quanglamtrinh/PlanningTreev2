# Post-Happy-Path to Final-Target Plan

Status: implementation roadmap. This doc describes the remaining work after the V1 happy-path milestone for execution and finished-leaf audit is complete.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-redesign-overview.md`
- `docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md`
- `docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md`
- `docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md`
- `docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md`

## Purpose

The happy-path milestone proves the product workflow:

- `Confirm and Finish Task` starts execution
- execution can accept follow-up implementation messages
- execution completion exposes `Mark Done` and `Review in Audit`
- local review runs on a detached review thread
- local review completion exposes `Mark Done` and `Improve in Execution`
- the loop can reach `done`

That milestone is sufficient to validate the product interaction model, but it is not yet the final target architecture described by the redesign docs.

This roadmap covers the remaining work required to move from the current happy-path implementation to the final target for:

- execution after `Finish Task`
- finished-leaf local audit/review

This roadmap does not change the already-decided scope boundary:

- `ask_planning` remains on the existing conversation path
- review-node flow remains out of scope for this rework
- legacy `/v1` behavior remains until a later cutover phase

## Current Baseline

The current implementation already has these properties:

- `workflow-state` is authoritative for workflow phase, thread IDs, and CTA gating
- execution and review surfaces select transcript by app-server `threadId`
- execution follow-up is supported on the execution surface
- first local review creates a detached review thread and later cycles reuse it
- audit before first local review renders metadata shell only
- review guidance and canonical frame/spec snapshots are injected into the audit/review thread

The current implementation is still transitional in these ways:

- transcript transport still passes through PTM adapter and projector logic instead of using a fully client-owned `thread/read` plus raw-event model end to end
- `GET /workflow-state` does not yet do the full reconcile-before-return behavior required by the final docs
- resume after refresh or restart is not yet a supported correctness path for execution or local review
- retry and restart recovery by persisted `clientRequestId` are not yet implemented as final-target workflow behavior
- `requestUserInput` is still unsupported in execution and local review
- local review read-only behavior is still guided mostly by instruction, not by a runtime-enforced capability profile
- some legacy metadata and polling behavior still exist around `detail-state` and document-editor surfaces

## Final-Target Gaps

The remaining gap to final target falls into five areas.

### 1. Transcript Architecture

Final target requires:

- execution and review transcript live path = `raw app-server event -> client reducer -> UI`
- transcript reload path = `client thread service -> thread/read -> hydrate client state`
- no backend-canonical execution/review transcript snapshot model

Current happy-path implementation still uses a PTM adapter path:

- `/v2/.../threads/by-id/{thread_id}` resolves back through PTM workflow service
- PTM still maps the active `threadId` back to a lane/role to read and stream transcript
- live events still rely on PTM thread snapshot/projector infrastructure

### 2. Reconciliation and Recovery

Final target requires:

- `GET /workflow-state` must reconcile before returning while the lane is non-terminal
- mutating workflow actions must reconcile before validation
- retry and adoption must reconcile by persisted `clientRequestId`
- restart or refresh must recover in-progress execution/review ownership without duplicate starts
- lane-local start states such as `starting` and `start_failed` must be first-class persisted state

Current happy-path implementation only covers the straight-line success path plus basic idempotency caching.

More specifically, the current happy-path milestone does not yet guarantee:

- resume after browser refresh during an active execution or active local review
- retry after a pre-start failure or ambiguous start outcome
- restart-safe recovery of in-flight execution or review ownership
- reconcile-by-`clientRequestId` before deciding whether a new turn or review cycle should be started

### 3. Runtime `requestUserInput`

Final target requires:

- client-owned pending-request queue
- `runtimeBlock = waiting_user_input`
- UI gating that disables generic send while a request is active
- refresh/reopen recovery through `thread/read`

Current happy-path implementation explicitly treats `requestUserInput` as unsupported.

### 4. Runtime-Enforced Review Safety

Final target requires local review to run with a runtime-enforced read-only capability profile.

Current happy-path implementation improves correctness by:

- running review on a detached review thread
- setting the right workspace root
- injecting explicit review guidance

But the actual read-only guarantee is still not fully encoded as an enforced runtime capability contract.

### 5. Contract Cleanup and Cutover

Final target requires:

- cleaner separation between `workflow-state`, `detail-state`, and transcript transport
- removal of transitional adapter assumptions for execution/review transcript
- strong regression coverage for restart, refresh, retry, and request-user-input paths

The happy-path implementation still contains transitional behavior that is acceptable for the milestone but not ideal for the final architecture.

## Phase Plan

### Phase 0: Runtime and UX Hardening

Objective:

- remove noisy runtime failures that make later phases harder to validate

Work:

- standardize Windows-safe command guidance for execution and review turns
- avoid known PowerShell parser traps such as `&&`
- prefer `npm.cmd` over bare `npm` in Windows runtime guidance where needed
- keep canonical frame/spec injection and review guidance stable
- improve fallback handling for `reviewDisposition` so workflow records remain structurally useful even when the runtime omits a disposition

Exit criteria:

- review and execution no longer fail for trivial Windows command-formatting reasons
- review summary and decision records remain consistent across successful runs

Why this phase boundary matters:

- later phases depend on runtime behavior being quiet enough that transport or reconcile bugs are easy to isolate

### Phase 1: Finalize ThreadId Transcript Transport

Objective:

- move execution and finished-leaf audit transcript transport to a true `threadId`-native model

Work:

- rework `/v2/.../threads/by-id/{thread_id}` into a thin transcript proxy keyed directly by app-server `threadId`
- rework `/v2/.../threads/by-id/{thread_id}/events` into a thin raw-event stream keyed directly by app-server `threadId`
- stop resolving the active execution/review transcript back through PTM lane-role assumptions for snapshot hydration
- keep `workflow-state` as the source of which `threadId` should hydrate, but not as the transcript transport itself
- update the frontend thread-by-id store so reducer state is the canonical client transcript state for execution and local review

Files and areas likely affected:

- `backend/routes/workflow_v2.py`
- `backend/services/execution_audit_workflow_service.py`
- `backend/conversation/services/thread_query_service.py`
- `frontend/src/features/conversation/state/threadByIdStoreV2.ts`

Exit criteria:

- execution and local review transcript reload comes from `thread/read`
- live execution and local review transcript updates come from raw app-server events
- PTM no longer depends on backend-built `THREAD_SNAPSHOT` as the canonical transport format for reworked lanes

Why this phase boundary matters:

- this is the core architectural shift that makes the transcript path match the redesign docs

### Phase 2: Add Reconcile-Before-Return and Restart Recovery

Objective:

- make workflow-state authoritative even after refresh, restart, partial failure, or duplicate mutation attempts

Work:

- add reconcile-before-return behavior to `GET /workflow-state` while execution or review is non-terminal
- add reconcile-before-validation behavior to workflow mutations
- persist and use lane-local start state such as:
  - `execution_start_state`
  - `audit_start_state`
- support `starting` and `start_failed` without inventing extra top-level workflow phases
- reconcile execution runs and review cycles by persisted `clientRequestId`
- support detached review-thread adoption when the review thread exists but PTM has not yet persisted it
- add restart-safe recovery for in-flight execution and local review

Files and areas likely affected:

- `backend/services/execution_audit_workflow_service.py`
- `backend/storage/workflow_state_store.py`
- `backend/storage/execution_run_store.py`
- `backend/storage/review_cycle_store.py`
- workflow reconciliation helpers and startup/reload paths

Exit criteria:

- refresh or backend restart during execution/review does not create duplicate starts
- retry reuses the existing run or review cycle when one is already confirmed
- `workflow-state` reports recovered authoritative state instead of stale optimistic state
- resume and retry are real supported behaviors instead of best-effort happy-path assumptions

Why this phase boundary matters:

- the final architecture depends on workflow-state being correct under non-happy-path conditions, not just in a single uninterrupted run

### Phase 3: Enforce Read-Only Review Runtime

Objective:

- make local review safety runtime-enforced rather than guidance-only

Work:

- add a dedicated read-only capability profile for review turns
- ensure `review/start` uses the read-only profile end to end
- preserve access to:
  - target commit diff
  - changed files
  - relevant test commands
  - canonical frame/spec snapshots already present in thread context
- prevent write-capable execution tools from being available to local review

Files and areas likely affected:

- `backend/ai/codex_client.py`
- `backend/services/execution_audit_workflow_service.py`
- app-server review-start contract handling

Exit criteria:

- local review can inspect but not mutate workspace state
- read-only behavior is guaranteed by runtime configuration, not only by prompt instruction

Why this phase boundary matters:

- this is the main safety property that distinguishes the final review model from an ordinary detached thread

### Phase 4: Implement Runtime `requestUserInput`

Objective:

- add the last major runtime feature missing from the execution and local-review lanes

Work:

- move pending request ownership into the client reducer path
- support `requestUserInput` for execution and local review
- store lane-local request state in `workflow-state` using `runtimeBlock` and active request metadata
- disable generic execution send while a request is active
- disable generic review mutation flow while a review request is active
- support refresh and reopen by rebuilding pending requests from `thread/read`

Files and areas likely affected:

- `frontend/src/features/conversation/state/threadByIdStoreV2.ts`
- `frontend/src/features/conversation/state/applyThreadEvent.ts`
- `backend/ai/codex_client.py`
- workflow-state models and APIs

Exit criteria:

- `requestUserInput` is functional in execution and local review
- refresh while waiting for user input restores the active request correctly
- unsupported-request errors are removed from the reworked lanes

Why this phase boundary matters:

- this is the last large functional gap between the happy-path milestone and the intended runtime behavior of the redesign

### Phase 5: Contract Cleanup and Surface Simplification

Objective:

- remove transitional behavior that is no longer needed once transcript transport and recovery are in place

Work:

- reduce legacy metadata refresh and polling paths around the reworked surfaces
- ensure `detail-state` remains metadata-only in both behavior and code structure
- optionally add a clean `/v2 detail-state` route if that improves contract clarity
- review whether execution thread creation should move earlier to `Confirm and Create Spec`
- clean up any remaining role-keyed assumptions inside reworked execution/audit surfaces

Files and areas likely affected:

- `frontend/src/features/node/NodeDocumentEditor.tsx`
- `frontend/src/stores/detail-state-store.ts`
- `frontend/src/features/conversation/state/workflowEventBridge.ts`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
- any transitional API facade kept only for the happy-path milestone

Exit criteria:

- reworked execution and finished-leaf audit surfaces no longer rely on legacy behavior beyond explicitly retained scope boundaries
- contract boundaries are easy to explain:
  - `workflow-state` for workflow truth
  - `detail-state` for metadata shell
  - `thread/read` plus raw events for transcript truth

Why this phase boundary matters:

- this phase reduces long-term maintenance cost and makes the final architecture legible to future contributors

### Phase 6: Cutover Validation and Cleanup

Objective:

- prove the final-target model under realistic failure and recovery conditions, then remove obsolete transitional assumptions for reworked lanes

Work:

- add integration and end-to-end coverage for:
  - execution follow-up
  - review detach and reuse
  - improve loop
  - refresh mid-turn
  - backend restart mid-turn
  - `requestUserInput`
  - duplicate mutation replay with same `clientRequestId`
- confirm `ask_planning` and review-node flow remain stable on their existing path
- remove transitional execution/review transcript assumptions that are no longer needed after full cutover

Exit criteria:

- the reworked execution and finished-leaf audit lanes satisfy the final redesign docs
- restart, refresh, retry, and request-user-input behavior are all covered by automated tests
- the remaining legacy paths are only the ones intentionally kept out of this rework

Why this phase boundary matters:

- the rework should only be considered complete when the final architecture is stable under the non-happy-path cases that motivated the redesign

## Recommended Sequencing

Recommended order:

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

This order is preferred because:

- transcript transport should match the target architecture before deeper runtime features are added
- reconcile and recovery should exist before `requestUserInput` expands runtime state complexity
- review safety should be runtime-enforced before the final cutover is considered trustworthy

## Completion Definition

The execution and finished-leaf audit rework should be considered fully complete only when all of the following are true:

- transcript transport is truly `threadId`-native and client-owned
- `workflow-state` reconciles and recovers correctly under refresh and restart
- retry and adoption are driven by persisted `clientRequestId`
- execution and local review both support `requestUserInput`
- local review runs with a runtime-enforced read-only profile
- automated coverage exists for both happy-path and post-happy-path recovery behavior

Until then, the current implementation should be described as:

- product-complete for V1 happy-path
- architecturally transitional relative to the final redesign target
