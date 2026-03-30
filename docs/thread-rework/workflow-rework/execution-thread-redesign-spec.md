# Execution Thread Redesign Spec

Status: draft redesign spec. Defines the target architecture for the execution thread under the explicit `Mark Done` / `Review in Audit` workflow.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md`
- `docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md`
- `docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md`

## Intent

The execution thread is no longer a semi-freeform backend-projected transcript. It becomes a dedicated implement-and-fix run surface with these properties:

- it starts from `Finish Task`, `Improve in Execution`, or a follow-up execution message
- it renders live transcript directly from raw app-server thread events
- it reloads by reading thread history directly from `thread/read`
- it never auto-triggers review
- when a run completes, the user chooses the next workflow action outside the live turn:
  - `Mark Done`
  - `Review in Audit`
  - or another follow-up execution message

The execution thread should feel as close as practical to CodexMonitor for transcript behavior while preserving PTM workflow correctness.

## 1. Ownership

### Browser / Frontend owns

- live execution transcript rendering
- raw event merge into execution thread items
- follow-up execution message entry in standard workflow mode
- semantic view-state:
  - grouped tools
  - reasoning presentation
  - working indicator
  - local scroll and expansion state
- local runtime user-input rendering and queueing
- transcript resume and reconnect behavior

### Backend owns

- `Finish Task` and `Improve in Execution` orchestration
- execution prompt construction
- `ExecutionRun` creation and persistence
- workflow phase transitions
- drift validation for post-run decisions
- Git commit on `Mark Done` and `Review in Audit`
- lane-local start-state persistence and error recovery
- decision reconciliation after restart or refresh

### App-server owns

- raw execution thread event stream
- `thread/read` transcript history
- authoritative raw turn lifecycle for the live thread

### Explicit non-ownership

Backend does not own:

- per-delta execution transcript projection
- server-built `hydratedItems` for reload
- execution prefix rendering
- semantic transcript grouping state

Browser does not own:

- workflow decisions
- accepted SHA
- task completion truth

### Source-of-truth split

- transcript source of truth: app-server thread plus browser reducer state
- workflow source of truth: backend `ExecutionRun` and node workflow state
- prefix metadata source of truth: backend workflow and detail state

In v1, PTM does not maintain a separate local execution transcript archive. Reopen and refresh rely on `thread/read`.

## 2. Transport

### Live transport model

Execution transcript follows the same shape as CodexMonitor:

- raw app-server event
- frontend reducer
- UI

Execution transcript event sources include:

- `item/started`
- `item/completed`
- `item/agentMessage/delta`
- `item/plan/delta`
- `item/reasoning/*`
- `item/commandExecution/*`
- `item/fileChange/*`
- `turn/completed`

### Transcript bootstrap model

Execution transcript bootstrap is client-owned:

1. frontend gets `executionThreadId` from workflow-state or detail-state
2. frontend client thread service calls `thread/read`
3. frontend converts returned thread payload into execution items
4. frontend hydrates local reducer state
5. frontend subscribes to live execution events if the turn is still active

### Metadata bootstrap model

Execution prefix and CTA metadata are fetched separately from backend workflow/detail APIs:

- task title
- frame/spec summary
- workflow phase
- CTA flags
- candidate artifact metadata

This metadata is rendered separately from transcript and must not block execution transcript hydration.

### Transport rules

- browser never starts execution turns directly against the app-server
- all turn creation still goes through backend workflow actions or execution follow-up endpoint
- client transport layer owns reconnect and resubscribe behavior
- PTM workflow API does not own a thread-scoped transport descriptor in v1

## 3. Runtime Reconciliation

Backend does not need to be authoritative for every runtime lifecycle edge.

What backend must persist for the execution lane:

- `executionStartState = idle | starting | started | start_failed`
- `executionLastError`
- current execution decision identity and supersession
- the persisted execution-turn `clientRequestId` while a start attempt is in flight
- `runtimeBlock = none | waiting_user_input`
- `activeRequestId`

Backend may reconcile terminal execution state from app-server lifecycle or from `thread/read`.

That reconciliation is used to:

- materialize the current execution decision after a run completes
- recover `start_failed` after restart or refresh
- adopt an execution turn that already exists for the persisted `clientRequestId`
- keep or restore the prior decision if a follow-up or improve attempt failed before turn confirmation
- keep CTA gating authoritative in workflow state

Required trigger points:

- `GET /workflow-state` must reconcile before returning while execution lane is non-terminal
- mutating workflow actions must reconcile before validation
- retry attempts must reconcile before validation

Per-delta transcript projection remains explicitly out of scope.

## 4. Hydration

### Initial load

Hydration for execution comes from two independent sources:

- transcript from app-server `thread/read`
- metadata from backend workflow/detail state

The browser must:

1. fetch workflow/detail state to learn `executionThreadId` and CTA metadata
2. call `thread/read` for that `executionThreadId`
3. build execution thread items locally
4. seed local reducer state
5. subscribe to live execution events if the thread is active

### Hydration rules

- transcript item IDs come from app-server items
- live events must patch the same reducer model used for hydrated items
- CTA state must never be derived from transcript items
- prefix metadata must not be injected into transcript item hydration

### Refresh behavior

On browser refresh while execution is active:

1. client discards in-memory reducer state
2. client refetches workflow/detail state
3. client calls `thread/read`
4. client rebuilds execution items locally
5. client resubscribes to live execution events
6. workflow state stays authoritative from backend

### Hydration responsibility boundary

- `thread/read` is responsible for transcript recovery
- workflow-state is responsible for decision-state recovery
- detail-state is responsible for PTM-specific execution metadata not embedded in transcript

Note:

- app-server history may be backed by Codex-managed local storage such as `.codex`
- PTM treats that storage as an app-server implementation detail
- PTM integrates only through `thread/read`, not by reading `.codex` directly

## 5. Platform Session Constraint

PTM v1 execution flow officially supports:

- one Electron app instance
- one active window
- no multi-tab workflow

Implications:

- execution does not require backend multi-tab coordination in v1
- request-user-input duplicate submission risk is reduced by platform design
- future multi-window or multi-tab support would require a new explicit design

## 6. User Input

### Supported user input paths

Execution supports two distinct user inputs:

- freeform follow-up execution messages from the user
- runtime `requestUserInput` emitted by the execution turn

### Freeform execution messages

Allowed when:

- workflow phase = `execution_decision_pending`
- no execution run is active
- no review cycle is active

These messages create a new `ExecutionRun(trigger_kind = "follow_up_message")`.

### Runtime requestUserInput

If execution emits `requestUserInput`:

1. client receives the raw request event
2. client adds the request to local request queue state
3. UI renders the input request inline
4. submitted answers go to backend action for resolution
5. backend forwards resolution to runtime and keeps lane state consistent

Rules:

- request queue ownership is client-side, matching CodexMonitor-style reducer behavior
- backend remains authoritative for resolving the request with runtime
- while `runtimeBlock = "waiting_user_input"`, generic execution send is disabled and only the active request may be answered
- if `thread/read` cannot reconstruct a pending request after refresh, PTM may add a thin fallback request-state endpoint later, but that is not part of the transcript critical path in v1

## 7. Terminal and Error Handling

### Terminal truth split

There are two terminal signals:

- transcript terminal signal from raw thread events
- workflow terminal signal from backend decision reconciliation

Rules:

- transcript may visually finish before workflow-state updates
- CTA buttons open only from backend workflow-state
- if transcript looks terminal but workflow-state is still running, UI shows terminal transcript plus pending workflow state
- if workflow-state is terminal but transcript missed the last event, client must refetch via `thread/read`

### Failure handling

Execution failures and start failures stay attached to the execution lane.

Rules:

- `start_failed` must render inline in the execution thread surface
- the execution thread surface must show the persisted error message and retry affordance
- retry uses the same public action endpoint and the same idempotency key semantics as the original action attempt
- retry must reconcile by the persisted execution `clientRequestId` before starting another execution turn
- a follow-up or improve request supersedes the previous decision only after the new execution turn is confirmed
- if the new execution turn is not confirmed, the prior decision and prior top-level phase remain or are restored
- retry execution remains in the execution lane
- transcript remains visible from `thread/read`

### Browser disconnect

If browser disconnects or closes:

- transcript live updates stop locally
- backend reconciliation remains correct
- reopen recovers transcript from `thread/read`

## 8. Migration Steps

1. Keep backend workflow endpoints and decision reconciliation as the authoritative control plane.
2. Remove execution UI dependence on backend-projected per-delta transcript snapshots.
3. Add a client execution thread service that reads execution transcript from `thread/read` and subscribes to live raw events.
4. Move execution request-user-input queue ownership into the client reducer path.
5. Move execution prefix rendering to workflow/detail metadata instead of transcript bootstrap.
6. Keep execution composer enabled for follow-up implement turns in `execution_decision_pending`.
7. Treat any existing backend `thread view` bootstrap endpoint as transitional only, not target architecture.

## Acceptance Criteria

- execution transcript live path is `raw event -> client reducer -> UI`
- execution reload path is `client thread service -> thread/read -> hydrate client state`
- backend no longer builds `hydratedItems` for execution as the target model
- execution prefix metadata is fetched separately from workflow/detail state
- execution composer remains available for follow-up implement turns
- runtime `requestUserInput` queue is client-owned
- backend decision state remains authoritative for workflow correctness
- PTM relies on `thread/read` rather than a separate PTM-owned execution transcript archive in v1
