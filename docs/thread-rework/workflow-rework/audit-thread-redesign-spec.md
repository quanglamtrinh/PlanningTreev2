# Audit Thread Redesign Spec

Status: draft redesign spec. Defines the target architecture for the audit lane under the explicit `Review in Audit` / `Improve in Execution` workflow.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md`
- `docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md`
- `docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md`

## Intent

The audit lane is no longer a single mixed chat surface.

It is split into:

- an audit lineage thread
- a review thread

The target behavior is:

- audit lineage thread remains the canonical context/source-of-truth thread for the node
- local code review does not happen directly in the audit lineage thread
- first local review creates a detached review thread from the audit lineage thread
- later local reviews continue on that same review thread
- the audit tab shows readonly metadata before first review, then shows the review thread transcript after it exists
- when local review completes, the user chooses:
  - `Mark Done`
  - `Improve in Execution`

This keeps lineage/context stable while using app-server review mode for actual review execution.

## 1. Thread Roles

### Audit lineage thread

Purpose:

- canonical node context
- frame and node-local `spec.md`
- inherited parent clarify and split context
- readonly audit metadata source for finished leaf nodes

The `spec.md` reference is node-local task context. It is not a repo-global hardcoded path such as `docs/spec.md`.

Rules:

- remains the canonical audit/context thread for the node
- is not the main live review transcript surface after a review thread exists
- is readonly in standard workflow mode after `Finish Task`
- may still be used as the source thread for the first detached `review/start`

### Review thread

Purpose:

- canonical local-review history thread for a finished leaf node
- runtime surface for app-server review mode
- source of canonical local review output

Rules:

- first created by `review/start(detached)` from the audit lineage thread
- later reused by `review/start` on that same review thread
- transcript is hydrated from `thread/read`
- canonical output is `exitedReviewMode.review`

### Non-leaf audit nodes

For non-leaf nodes:

- audit lineage remains readonly context
- local review thread flow does not activate
- final subtree review belongs to the review-node flow and is out of scope here

## 2. Ownership

### Browser / Frontend owns

- live review transcript rendering
- raw review event merge into thread items
- semantic view-state for review transcript
- local row expansion, grouped tools, scroll state, and viewport state
- structured runtime user-input presentation and queueing if the review turn requests it
- transcript resume and reconnect behavior
- readonly audit metadata shell before the first local review exists

### Backend owns

- `Review in Audit` orchestration
- `ReviewCycle` creation and persistence
- workflow phase transitions
- `Mark Done` and `Improve in Execution` decision correctness
- lane-local start-state persistence and error recovery
- retrieval and persistence of `exitedReviewMode.review`
- review-turn reconciliation by `clientRequestId`, including detached review-thread adoption

### App-server owns

- raw audit lineage thread event stream
- raw review-thread event stream
- `thread/read` transcript history
- authoritative raw turn lifecycle for review turns
- review-mode items such as `enteredReviewMode` and `exitedReviewMode`

### Explicit non-ownership

Backend does not own:

- per-delta review transcript projection
- server-built `hydratedItems` for reload
- audit prefix rendering
- client semantic grouping state

Browser does not own:

- review-cycle identity
- accepted implementation state
- whether review findings require another execution run

### Source-of-truth split

- audit lineage source of truth: app-server audit lineage thread plus backend metadata
- review transcript source of truth: app-server review thread plus browser reducer state
- workflow source of truth: backend `ReviewCycle` and `workflow-state`
- display metadata source of truth: backend `detail-state` plus display mirrors from `workflow-state`

In v1, PTM does not maintain a separate local review transcript archive. Reopen and refresh rely on `thread/read`.

## 3. Transport

### Live transport model

Review transcript follows the same shape as CodexMonitor:

- raw app-server event
- frontend reducer
- UI

Relevant review transcript event sources include:

- `turn/started`
- `item/started`
- `item/completed`
- `item/agentMessage/delta`
- `item/reasoning/*`
- `item/plan/delta`
- `item/commandExecution/*`
- `turn/completed`

Review-mode specific items include:

- `enteredReviewMode`
- `exitedReviewMode`

### Transcript bootstrap model

Audit UI bootstrap depends on whether a review thread already exists.

Before first local review:

1. frontend gets `auditLineageThreadId`, `reviewThreadId`, workflow phase, and CTA metadata from `workflow-state`
2. frontend may fetch `detail-state` in parallel for readonly audit shell context
3. frontend sees `reviewThreadId = null`
4. frontend renders readonly audit metadata shell only

After first local review exists:

1. frontend gets `reviewThreadId` from `workflow-state`
2. frontend client thread service calls `thread/read`
3. frontend converts returned thread payload into review items
4. frontend hydrates local reducer state
5. frontend subscribes to live review-thread events if the turn is still active

### Metadata bootstrap model

Audit prefix and CTA metadata are fetched separately from backend APIs:

- `workflow-state` provides:
  - `auditLineageThreadId`
  - `reviewThreadId`
  - `workflowPhase`
  - CTA flags
  - runtime block and active request state
  - `latestReviewCycleId`
  - `latestReviewCommitSha`
  - `latestReviewDisposition`
  - current audit decision metadata
- `detail-state` provides:
  - task title
  - node-local frame/spec summary
  - parent clarify and split context
  - readonly shell metadata that is not workflow control truth

This metadata is rendered separately from transcript and must not block review transcript hydration.

If a mirrored field conflicts across the two APIs, `workflow-state` wins for thread identity, runtime state, CTA gating, and workflow validation.

### Transport rules

- browser never starts review turns directly against the app-server
- browser only consumes transcript events directly
- all review-cycle creation still goes through backend workflow action `Review in Audit`
- client review thread service is keyed by `reviewThreadId`, not by `(projectId, nodeId, threadRole)`
- client transport layer owns reconnect and resubscribe behavior
- PTM workflow API does not own a thread-scoped transport descriptor in v1
- review turns must run with a runtime-enforced read-only capability profile
- review turns must not mutate workspace state, apply patches, write files, or create commits
- any mutation-capable tool call from local review must be rejected by runtime
- read-only inspection commands are allowed

## 4. Review Cycle Model

One `ReviewCycle` corresponds to one reviewed commit and one review turn.

Suggested shape:

```ts
type ReviewDisposition = "approved" | "changes_requested";
```

```ts
type ReviewCycle = {
  cycleId: string;
  sourceExecutionRunId: string;
  auditLineageThreadId: string;
  reviewThreadId: string | null;
  reviewTurnId: string | null;
  reviewCommitSha: string;
  deliveryKind: "detached" | "inline";
  clientRequestId: string;
  finalReviewText: string | null;
  lifecycleStatus: "running" | "completed" | "failed" | "superseded";
  reviewDisposition: ReviewDisposition | null;
  errorMessage: string | null;
};
```

Rules:

- `reviewCommitSha` is the authoritative reviewed artifact field
- `finalReviewText` comes from `exitedReviewMode.review`
- `reviewDisposition` is reviewer metadata; user workflow decisions still live in backend audit decision state
- cycle 1 usually uses `deliveryKind = "detached"`
- later cycles on the same leaf node use `deliveryKind = "inline"`
- backend must bind `finalReviewText` to `reviewTurnId`, not to "the latest review-looking item in the thread"

## 5. Runtime Reconciliation

Backend does not need to project or own every audit lifecycle delta.

What backend must persist for the audit lane:

- `auditStartState = idle | starting | started | start_failed`
- `auditLastError`
- current audit decision identity and reviewed commit
- `runtimeBlock = none | waiting_user_input`
- `activeRequestId`
- `reviewThreadId` if known
- `reviewTurnId` if known
- `clientRequestId`
- `finalReviewText` if the review completed
- `reviewDisposition` if the review completed

Backend may reconcile review completion from app-server lifecycle or from `thread/read`.

That reconciliation is used to:

- materialize the current audit decision after review completes
- recover `start_failed` after restart or refresh
- capture `exitedReviewMode.review` for `Improve in Execution` v1
- adopt a detached review thread that was created before backend persisted `reviewThreadId`
- adopt an inline review turn that was created before backend persisted `reviewTurnId`
- keep reviewer disposition separate from workflow decision state

Required trigger points:

- `GET /workflow-state` must reconcile before returning while the audit lane is non-terminal
- mutating workflow actions must reconcile before validation
- retry attempts must reconcile before validation

## 6. Hydration

### Initial load

Hydration for the audit tab comes from two independent sources:

- transcript from app-server `thread/read` when `reviewThreadId` exists
- metadata from backend `workflow-state` and `detail-state`

The browser must:

1. fetch `workflow-state` to learn `auditLineageThreadId`, `reviewThreadId`, CTA metadata, and runtime state
2. optionally fetch `detail-state` in parallel for audit shell metadata
3. if `reviewThreadId` is `null`, render readonly metadata shell and stop there
4. if `reviewThreadId` is present, call `thread/read` for that `reviewThreadId`
5. build review-thread items locally
6. seed local reducer state
7. subscribe to live review events if the thread is active

### Hydration rules

- transcript item IDs come from app-server items
- live events patch the same reducer model as hydrated items
- audit CTA state must never be derived from transcript interpretation
- review metadata prefix must not be injected into transcript hydration
- audit lineage thread is not the primary transcript surface after first review thread creation
- once `reviewThreadId` exists, the standard audit transcript surface hydrates exclusively from that `reviewThreadId`

### Refresh behavior

On browser refresh while review is active:

1. local reducer state is discarded
2. client refetches `workflow-state` and optionally `detail-state`
3. client calls `thread/read` for the current `reviewThreadId`
4. client rebuilds review items locally
5. client resubscribes to live review events
6. workflow state remains authoritative from backend

Note:

- app-server history may be backed by Codex-managed local storage such as `.codex`
- PTM treats that storage as an app-server implementation detail
- PTM integrates only through `thread/read`, not by reading `.codex` directly

## 7. Platform Session Constraint

PTM v1 audit flow officially supports:

- one Electron app instance
- one active window
- no multi-tab workflow

Implications:

- audit does not require backend multi-tab coordination in v1
- runtime request input is handled in a single visible thread surface
- future multi-window or multi-tab support would require a new explicit design

## 8. User Input

### Supported user input paths

Audit does not allow generic freeform user messages in standard workflow mode.

Audit only supports:

- runtime `requestUserInput` emitted by the active review turn
- decision actions after review completes

### Runtime requestUserInput

If local review emits `requestUserInput`:

1. client receives the raw request event
2. client adds the request to local request queue state
3. UI renders the input request inline
4. submitted answers go to backend action for resolution
5. backend forwards resolution to runtime and keeps lane state consistent

Rules:

- request queue ownership is client-side, matching CodexMonitor-style reducer behavior
- backend remains authoritative for resolving the request with runtime
- while `runtimeBlock = "waiting_user_input"`, generic send remains disabled and only the active request may be answered
- if `thread/read` cannot reconstruct a pending request after refresh, that is a correctness bug for this rework and a blocker for shipping the audit lane; v1 does not define a fallback request-state endpoint

## 9. Terminal and Error Handling

### Terminal truth split

There are two terminal signals:

- transcript terminal signal from raw thread events
- workflow terminal signal from backend decision reconciliation

Rules:

- transcript may visually finish before workflow-state updates
- `Mark Done` and `Improve in Execution` open only from backend workflow-state
- if transcript looks terminal but workflow-state is still running, UI shows terminal transcript plus pending workflow state
- if workflow-state is terminal but transcript missed the last event, client must refetch via `thread/read`

### Failure handling

Audit failures and start failures stay attached to the audit lane.

Rules:

- `start_failed` must render inline in the audit surface
- the audit surface must show the persisted error message and retry affordance
- retry uses the same public action endpoint and the same idempotency key semantics as the original action attempt
- if commit already succeeded, retry must reuse the same `reviewCommitSha`
- first detached review retry must reconcile by `clientRequestId` before trying detached creation again
- later retries on an existing `reviewThreadId` must also reconcile by `clientRequestId` before rerunning `review/start` on that review thread
- transcript remains visible from `thread/read` when a review thread already exists

### Browser disconnect

If browser disconnects or closes:

- transcript live updates stop locally
- backend reconciliation remains correct
- reopen recovers transcript from `thread/read`

## 10. Migration Steps

1. Keep backend workflow endpoints and decision reconciliation as the authoritative control plane.
2. Stop treating the audit lineage thread as the live local-review transcript surface.
3. Add client review-thread hydration from `thread/read` and live raw review events.
4. Keep audit tab metadata rendering from `workflow-state` and `detail-state` even before first local review exists.
5. Move review request-user-input queue ownership into the client reducer path.
6. Keep audit generic composer disabled in standard workflow mode.
7. Treat any existing backend `thread view` bootstrap endpoint as transitional only, not target architecture.

## Acceptance Criteria

- audit lineage remains the canonical node-context thread
- first local review creates a detached review thread from the audit lineage thread
- later local reviews continue on the same review thread
- audit tab renders readonly metadata when `reviewThreadId` is absent
- audit tab hydrates transcript from `reviewThreadId` when it exists
- audit transcript hydration is keyed by `reviewThreadId` from `workflow-state`
- review transcript live path is `raw event -> client reducer -> UI`
- review reload path is `client thread service -> thread/read -> hydrate client state`
- backend no longer builds `hydratedItems` for local review as the target model
- audit prefix metadata is fetched separately from `workflow-state` and `detail-state`
- review runtime remains read-only and never mutates workspace
- runtime `requestUserInput` queue is client-owned
- `Improve in Execution` v1 uses `exitedReviewMode.review`
- backend decision state remains authoritative for workflow correctness
- PTM relies on `thread/read` rather than a separate PTM-owned review transcript archive in v1
