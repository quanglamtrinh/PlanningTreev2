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
  - stale-stream mutations are rejected by ownership rules
  - reconnect cannot bind to the wrong stream
  - durable persistence produces replayable normalized conversation records
  - hot-path forwarding remains forward-first and persist-after
  - non-execution-eligible send is rejected without creating live ownership state

### Verification
- backend integration tests
- one execution-thread end-to-end stream
- reconnect and stale-stream rejection checks
- session-manager unit tests for reuse, isolation, reset, missing status, and shutdown
- execution-only route tests for durable-store-first snapshot behavior and non-execution-eligible send rejection

## Phase 3 - Shared Conversation Surface, Execution First
### Goal
- Make execution the first visible cutover.

### Scope
- shared conversation surface
- execution embedding
- basic assistant text streaming
- history load and replay

### Expected Files Or Folders To Change
- `frontend/src/features/conversation/components/`
- `frontend/src/features/breadcrumb/ChatPanel.tsx`
- `frontend/src/api/hooks.ts`

### Dependencies
- Phase 1 store
- Phase 2 gateway

### Out Of Scope
- ask and planning embedding
- advanced rich blocks beyond initial execution text stream

### Risks
- execution regression
- dual-path complexity during rollback window

### Acceptance Criteria
- execution uses the shared surface
- history loads
- streaming works
- rollback remains available

### Verification
- manual execution flow
- reload and replay check
- regression checks against existing execution framing

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
