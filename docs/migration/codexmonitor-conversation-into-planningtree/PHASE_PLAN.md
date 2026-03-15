# Phase Plan

## Phase 0 - Audit, Formalize Plan 1, And Create Artifacts
### Goal
- Finalize the architecture baseline and create the required migration artifacts.

### Scope
- source and target audit summary
- master plan formalization
- module mapping
- dependency map
- message model baseline
- gateway and session architecture baseline
- batch sequencing and validation baseline

### Expected Files Or Folders To Change
- `docs/migration/codexmonitor-conversation-into-planningtree/`
- optional feature spec under `docs/features/`

### Dependencies
- audited source modules from `CodexMonitor`
- audited target modules from `PlanningTreeMain`

### Out Of Scope
- broad UI cutover
- session manager implementation
- visible thread embedding changes

### Risks
- documentation drift
- hidden assumptions about identity or replay

### Acceptance Criteria
- all required artifacts exist
- identity, mode, persistence, runtime, rollout, and batch rules are explicit
- execution can begin without reopening baseline architecture decisions

### Verification
- all required files present
- module mapping and CSV agree
- master plan, phase plan, and gateway docs use the same identity and truth model

## Phase 1 - Conversation Foundations
### Goal
- Establish event schema, rich message schema, compatibility adapters, shared types, and keyed state foundations.

### Scope
- backend conversation contracts
- dedicated conversation store skeleton
- frontend conversation types
- frontend keyed conversation store
- compatibility adapters from current simple sessions

### Expected Files Or Folders To Change
- `backend/conversation/`
- `backend/storage/conversation_store.py`
- `backend/storage/storage.py`
- `frontend/src/features/conversation/`
- `frontend/src/stores/conversation-store.ts`

### Dependencies
- `backend/storage/file_utils.py`
- `frontend/src/api/types.ts`
- current `chat-store.ts` and `ask-store.ts`

### Out Of Scope
- gateway routing
- session manager
- visible UI replacement

### Risks
- shape divergence between backend and frontend contracts
- accidental coupling to singleton legacy state

### Acceptance Criteria
- contracts compile
- message model is documented
- replay source of truth is explicit
- no visible UI cutover required yet

### Verification
- backend unit tests for conversation store
- frontend unit tests for keyed store merge behavior
- frontend build passes

## Phase 2 - Thin Gateway And Session Manager
### Goal
- Implement the project-scoped session model first, then the execution-only conversation-v2 gateway path.

### Scope
- `P2.1` project-scoped `CodexSessionManager`
- `P2.2` execution-only `ConversationGateway`
- execution-only v2 `get`, `send`, and `events` routes in parallel to legacy routes
- stream ownership under project-session locks
- durable-store-first execution snapshot reads
- reconnect safety for execution SSE subscribers
- persistence integration with forward-first, persist-after hot-path rules

### Expected Files Or Folders To Change
- `backend/main.py`
- `backend/routes/`
- `backend/services/`
- `backend/streaming/`

### Dependencies
- Phase 1 contracts
- existing chat and ask services
- codex process management integration

### Out Of Scope
- broad ask or planning UI cutover
- ask or planning v2 routes
- ChatPanel replacement
- rich renderer migration

### Risks
- heavy hot-path proxying
- incorrect session reuse
- reconnect ownership bugs
- accidental dependence on the legacy app-global codex client

### Acceptance Criteria
- Phase 2 exit contract passes in full
- `P2.1` acceptance:
  - project-scoped session manager exists and is wired into app state
  - same-project reuse is proven
  - cross-project isolation is proven
  - missing-session health inspection is safe
  - legacy boot path still works
  - no new v2 code path depends on the legacy app-global client
- `P2.2` acceptance:
  - one execution-thread conversation streams end to end through the new v2 gateway
  - same-project session reuse works
  - cross-project isolation works
  - send-start emits exactly two `message_created` events with explicit `event_seq = n + 1` then `n + 2`
  - success path emits `assistant_text_final` before `completion_status(completed)`
  - error or interrupted terminal paths emit `completion_status(...)` without `assistant_text_final`
  - stale-stream mutations are rejected by ownership rules
  - reconnect cannot bind to the wrong stream
  - durable persistence produces replayable normalized conversation records
  - hot-path forwarding remains forward-first and persist-after
  - non-execution-eligible send is rejected without creating live ownership state
  - app shutdown flushes terminal and other high-value gateway persistence before session-manager shutdown

### Verification
- backend integration tests
- one execution-thread end-to-end stream
- reconnect and stale-stream rejection checks
- session-manager unit tests for reuse, isolation, reset, missing status, and shutdown
- execution-only route tests for durable-store-first snapshot behavior and non-execution-eligible send rejection

## Phase 3 - Shared Conversation Surface, Execution First
### Goal
- Make execution the first visible cutover.

### Canonical Tracking Names
- Use `Phase 3.1`, `Phase 3.2`, and `Phase 3.3` as the only primary tracking identifiers across migration docs and artifacts.
- "Part" may appear only as informal prose, not as the main tracking label.

### Overall Completion Rule
- Phase 3 is not considered complete until `Phase 3.3` is complete.
- Completion of `Phase 3.1` or `Phase 3.2` is necessary but not sufficient for Phase 3 completion.

### Dependencies
- Phase 1 store
- Phase 2 gateway

### Phase 3.1 - Execution Conversation Data Plumbing
#### Goal
- Establish the execution-only frontend v2 data path without switching the visible execution UI.

#### Scope
- execution-only v2 client methods
- keyed execution conversation state hydration
- snapshot-first load path
- SSE subscription and reconnect model
- send flow wiring to v2
- non-visible execution conversation plumbing

#### Out Of Scope
- visible execution transcript switch
- shared surface rollout
- ask and planning embedding
- shell migration
- wrapper cutover work

#### Risks
- state drift between legacy visible execution UI and the new non-visible execution conversation state
- reconnect handling bugs becoming harder to detect before the visible cutover lands

#### Acceptance Criteria
- execution conversation data can load, send, stream, and reconnect in frontend state through the v2 path
- no visible execution cutover happens yet
- legacy visible execution UI remains active

#### Rollback Note
- This phase is additive and non-visible; rollback is trivial because the legacy visible execution path remains intact.

#### Verification
- snapshot load works against the execution v2 `GET`
- SSE subscribe and reconnect behavior work in keyed frontend state
- send path is wired through the execution v2 `POST`
- no visible execution transcript switch occurs yet

### Phase 3.2 - Shared Conversation Surface Presentation
#### Goal
- Introduce the shared presentational conversation surface and the minimal render contract.

#### Scope
- shared conversation surface presentation
- minimal rendering for user text, assistant text, and streaming assistant text
- loading, error, and empty states
- safe degradation for unsupported rich parts

#### Out Of Scope
- visible execution transcript switch
- broad wrapper rewiring
- ask and planning embedding
- shell migration
- broad rich parity
- public retry, continue, regenerate, or cancel controls

#### Risks
- scope leakage between `Phase 3.2` and `Phase 3.3`
- presentational assumptions accidentally becoming host-integration constraints too early

#### Acceptance Criteria
- the shared surface exists and renders the minimal execution-first conversation contract
- unsupported parts degrade safely
- the surface is ready to be hosted by execution
- the visible execution transcript is still not switched by this phase alone

#### Rollback Note
- Rollback is contained to the presentational layer because execution host integration remains deferred.

#### Verification
- user and assistant text render correctly
- streaming assistant text renders correctly
- loading, error, and empty states render correctly
- unsupported rich parts degrade safely
- the visible execution transcript is still not switched by this phase

### Phase 3.3 - Execution Tab Visible Cutover
#### Goal
- Switch the execution tab to the new shared conversation surface while preserving execution framing and rollback safety.

#### Scope
- execution host integration
- visible execution transcript cutover
- visible composer and send path through v2
- execution-tab wrapper integration only as needed for the cutover
- preserve existing `Plan` / `Execute` framing and wrapper behavior

#### Out Of Scope
- ask embedding
- planning embedding
- shell migration
- broad parity work
- new public command controls
- architecture redesign

#### Risks
- execution regression during the visible cutover
- dual-path complexity during the rollback window
- wrapper regressions if host integration expands beyond execution

#### Acceptance Criteria
- execution tab visibly uses the new shared conversation surface
- snapshot load, stream subscription, send, and reconnect work through the v2 path
- execution framing remains intact
- rollback remains available

#### Rollback Note
- Rollback remains a contained host-level revert because ask/planning and shell work are still untouched.

#### Verification
- manual execution flow
- reload and replay check
- reconnect check in the execution tab
- regression checks against existing execution framing
- rollback path remains available

## Phase 4 - Ask And Planning Embedding
### Goal
- Reuse the same surface in ask and planning while preserving wrappers.

### Scope
- ask embedding
- planning embedding
- wrapper preservation

### Expected Files Or Folders To Change
- `frontend/src/features/breadcrumb/AskPanel.tsx`
- `frontend/src/features/breadcrumb/PlanningPanel.tsx`
- `frontend/src/features/conversation/`

### Dependencies
- execution cutover stability
- packet sidecar compatibility
- planning split control compatibility

### Out Of Scope
- shell changes

### Risks
- wrapper regressions
- planning composer confusion

### Acceptance Criteria
- ask packet sidecar remains intact
- planning split controls remain intact
- ask and planning both use the shared conversation surface

### Verification
- wrapper regression checklist
- manual ask and planning thread validation

## Phase 5 - Advanced Semantics And Rich Components
### Goal
- Reach CodexMonitor-like semantic parity for rich conversation behavior.

### Scope
- reasoning blocks
- tool and result cards
- plan blocks
- plan step status
- approval requests
- runtime input
- diff and file summaries
- retry, continue, regenerate, cancel controls

### Risks
- replay mismatch between live and persisted states

### Acceptance Criteria
- rich components render live and replay correctly
- lineage-aware actions work on the new path

### Verification
- event-to-part mapping tests
- replay fidelity tests

## Phase 6 - Performance, Concurrency, Replay, And Cleanup
### Goal
- Harden performance and concurrency and remove compatibility code only when safe.

### Scope
- latency improvements
- dense-event hardening
- concurrent stream validation
- reconnect hardening
- cleanup after cutover gates pass

### Risks
- over-eager cleanup
- hidden concurrency bugs

### Acceptance Criteria
- multiple threads stream concurrently without cross-cancel
- replay remains faithful
- cleanup is documented and gated

### Verification
- latency sanity checks
- dense-event stress checks
- concurrent stream checks
- replay fidelity checks
