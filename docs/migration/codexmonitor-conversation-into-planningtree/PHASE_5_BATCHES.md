# Phase 5 Batches

## Batch Sequencing Defaults
- Keep the target runnable after every batch.
- Keep batch IDs stable once work starts.
- Treat `5.1` as the replay and passive-normalization baseline for `5.2` and `5.3`.
- Keep host-specific shell or wrapper redesign out of scope.
- Do not claim backend live parity for semantics that remain replay-only or runtime-blocked.

## Phase 5.1 - Rich Passive Semantics And Renderer Parity

## P5.1.a
- Title: Contract locking and identity rules
- Status: Complete
- Objective:
  - lock canonical passive mapping rules, target identity rules, and fallback distinctions
- Exact scope:
  - passive part/event identity
  - deterministic assistant-only attachment
  - unknown-vs-malformed fallback policy
- Files or modules likely affected:
  - `frontend/src/features/conversation/types.ts`
  - `frontend/src/features/conversation/model/applyConversationEvent.ts`
  - `backend/conversation/contracts.py`
- Dependencies:
  - stable Phase 4 text-first conversation contract
- Implementation notes:
  - reject non-deterministic passive attachment
  - keep replay-only semantics explicit if the transport does not expose native live signals
- Risks:
  - hidden message attachment drift
- Done criteria:
  - canonical passive identity rules are documented and implemented

## P5.1.b
- Title: Reducer and render-model parity
- Status: Complete
- Objective:
  - make the shared conversation reducer and render model passive-part aware
- Exact scope:
  - passive event application
  - ordered render items
  - duplicate-delivery idempotency
- Files or modules likely affected:
  - `frontend/src/features/conversation/model/applyConversationEvent.ts`
  - `frontend/src/features/conversation/model/buildConversationRenderModel.ts`
- Dependencies:
  - `P5.1.a`
- Implementation notes:
  - preserve normalized part ordering inside a message
  - keep replay semantics independent from raw arrival order
- Risks:
  - duplicate passive blocks on reconnect
- Done criteria:
  - reducer and render-model tests cover deterministic ordering and idempotent upsert behavior

## P5.1.c
- Title: Shared passive renderers
- Status: Complete
- Objective:
  - render supported passive semantics on the shared surface instead of degrading them as unsupported content
- Exact scope:
  - shared passive blocks
  - safe malformed fallback
  - mixed text + passive transcript rendering
- Files or modules likely affected:
  - `frontend/src/features/conversation/components/ConversationBlocks.tsx`
  - `frontend/src/features/conversation/components/ConversationSurface.tsx`
- Dependencies:
  - `P5.1.b`
- Implementation notes:
  - semantic parity only; wrapper framing may still differ
- Risks:
  - leaking source-UI-specific shell behavior into the shared contract
- Done criteria:
  - known passive semantics render on the shared surface without crashing

## P5.1.d
- Title: Execution live-path mapping and persistence
- Status: In progress
- Objective:
  - implement backend live emission and persistence for transport-supported passive semantics on the execution path
- Exact scope:
  - `tool_call`
  - `plan_block`
  - terminal reconciliation
  - durable persistence
- Files or modules likely affected:
  - `backend/ai/codex_client.py`
  - `backend/services/conversation_gateway.py`
  - backend execution conversation tests
- Dependencies:
  - `P5.1.a`
  - `P5.1.b`
- Implementation notes:
  - current transport support is limited; keep other semantics replay-only
  - terminal reconciliation is merge/update, not blind overwrite
- Risks:
  - overstating backend live completeness
- Done criteria:
  - `tool_call` and `plan_block` live emission, persistence, and reconciliation are stable and documented

## P5.1.e
- Title: Planning and ask convergence
- Status: In progress
- Objective:
  - keep planning and ask aligned with the passive contract only where a clean normalized source exists
- Exact scope:
  - planning normalized passive replay
  - ask passive semantics where already normalizable
  - support-matrix documentation
- Files or modules likely affected:
  - planning and ask conversation adapters
  - docs and validation coverage
- Dependencies:
  - `P5.1.c`
  - `P5.1.d`
- Implementation notes:
  - do not invent fake live semantics where the source does not expose them
- Risks:
  - wrapper-owned shadow semantics
- Done criteria:
  - planning/ask claims remain aligned with actual normalized sources

## Phase 5.2 - Interactive Request/Response Semantics

## P5.2.a
- Title: Contract and lifecycle locking
- Status: Complete
- Objective:
  - lock interactive request/response semantics, lifecycle states, and active-request selection rules
- Exact scope:
  - `request_resolved`
  - durable `request_id`
  - `resolution_state`
  - latest-unresolved active request policy
- Files or modules likely affected:
  - `frontend/src/features/conversation/types.ts`
  - `backend/conversation/contracts.py`
  - docs
- Dependencies:
  - `P5.1.a`
- Implementation notes:
  - the active visible request is the latest unresolved request on the currently visible lineage
- Risks:
  - reopening stale historical requests after reconnect
- Done criteria:
  - lifecycle rules and active-request selection are documented and implemented

## P5.2.b
- Title: Reducer and render-model parity
- Status: Complete
- Objective:
  - make interactive request lifecycle first-class on the shared reducer and render model
- Exact scope:
  - `approval_request`
  - `request_user_input`
  - `request_resolved`
  - `user_input_resolved`
  - render items for request and response semantics
- Files or modules likely affected:
  - `frontend/src/features/conversation/model/applyConversationEvent.ts`
  - `frontend/src/features/conversation/model/buildConversationRenderModel.ts`
- Dependencies:
  - `P5.2.a`
- Implementation notes:
  - request parts update in place by `request_id`
  - user responses remain explicit conversation content
- Risks:
  - duplicate request or response UI on replay
- Done criteria:
  - known interactive semantics no longer degrade as unsupported content

## P5.2.c
- Title: Shared request renderers and host request-actions
- Status: Complete
- Objective:
  - add shared request renderers while keeping submit controls host-owned
- Exact scope:
  - read-only request/response blocks
  - shared request-actions hook
  - host modal or form integration
- Files or modules likely affected:
  - `frontend/src/features/conversation/components/ConversationBlocks.tsx`
  - `frontend/src/features/conversation/hooks/useConversationRequests.ts`
  - host wrappers such as `BreadcrumbWorkspace.tsx`
- Dependencies:
  - `P5.2.b`
- Implementation notes:
  - wrappers may differ in placement, but lifecycle state is conversation-owned
- Risks:
  - host wrappers keeping a second authoritative request queue
- Done criteria:
  - host-owned submit affordances derive from the same v2 request state as the transcript

## P5.2.d
- Title: Execution live path and resolve adapters
- Status: Complete
- Objective:
  - implement execution-native request lifecycle streaming, persistence, resolution, and duplicate-publish hardening
- Exact scope:
  - `on_request_user_input`
  - `on_request_resolved`
  - request-response persistence
  - idempotent resolve route
  - duplicate terminal-publish suppression for local resolve plus native callback overlap
- Files or modules likely affected:
  - `backend/ai/codex_client.py`
  - `backend/routes/conversation.py`
  - `backend/services/conversation_gateway.py`
- Dependencies:
  - `P5.2.a`
  - `P5.2.b`
- Implementation notes:
  - request-created and request-resolved writes are high-value flush events
  - guarded refresh is recovery only
  - route-driven execution resolution is the authoritative terminal publish path for locally initiated user-input resolution
- Risks:
  - request-resolution events racing behind completion
  - native callback double-publish after local resolve
- Done criteria:
  - execution runtime-input lifecycle is stable on the v2 path, suppresses duplicate terminal publish, and is covered by tests

## P5.2.e
- Title: Planning convergence and closeout
- Status: Complete
- Objective:
  - converge planning interactive semantics onto the shared v2 request contract where a clean normalized source exists and keep repo boundaries explicit
- Exact scope:
  - planner request-state normalization
  - planning v2 resolve route
  - planning host request ownership from v2 state
  - docs for runtime-blocked approval parity
  - ask/planning boundary validation
- Files or modules likely affected:
  - planning adapters
  - docs
  - validation coverage
- Dependencies:
  - `P5.2.c`
  - `P5.2.d`
- Implementation notes:
  - planning follows the same latest-unresolved active request policy as execution
  - do not imply ask convergence where the repo does not yet have a clean source
- Risks:
  - wrapper-owned shadow interactive state
  - orphan planning resolve events fabricating active request UI
- Done criteria:
  - planning runtime-input lifecycle is normalized onto the shared v2 contract, planning host request ownership derives from v2 state, and ask claims remain limited to real normalized sources

## Phase 5.3 - Lineage-Aware Actions And Command Semantics

## P5.3.a
- Title: Lineage metadata and supersession baseline
- Status: Complete
- Objective:
  - define the durable lineage model required for retry, continue, and regenerate
- Exact scope:
  - lineage identifiers
  - supersession markers
  - replayability of superseded branches
- Files or modules likely affected:
  - backend conversation contracts and persistence
  - frontend lineage-aware selectors
- Dependencies:
  - `P5.1`
  - `P5.2`
- Implementation notes:
  - lineage is durable state, not UI-only metadata
  - ordinary execution sends now seed `parent_message_id` for user and assistant messages
  - legacy execution transcripts are repaired lazily and idempotently before snapshot read or action validation
  - visible lineage selection uses the latest eligible unsuperseded execution assistant head by durable order
- Risks:
  - hidden loss of superseded history
- Done criteria:
  - durable lineage metadata and replay semantics are locked and implemented for the execution-first scope

## P5.3.b
- Title: Cancel semantics and terminalization policy
- Status: Complete
- Objective:
  - implement `cancel` as active-operation control on the current lineage
- Exact scope:
  - cancel request handling
  - ownership checks
  - cancel/completion race policy
- Files or modules likely affected:
  - backend gateway
  - frontend action wiring
  - tests
- Dependencies:
  - `P5.3.a`
- Implementation notes:
  - cancel must not fabricate a new branch
  - accepted cancel clears active stream ownership before late callbacks can restamp terminal state
- Risks:
  - cancel being implemented as pseudo-regenerate
- Done criteria:
  - cancel terminalizes the active lineage without branch creation

## P5.3.c
- Title: Retry, continue, and regenerate action surfaces
- Status: Complete
- Objective:
  - implement lineage-aware mutation semantics and explicit fallback behavior
- Exact scope:
  - action routing
  - runtime fallback policy
  - ownership and terminal-state rules
- Files or modules likely affected:
  - backend action routes
  - frontend action controls
  - lineage-aware reducers
- Dependencies:
  - `P5.3.a`
  - `P5.3.b`
- Implementation notes:
  - never imply true rewind if the runtime cannot provide it
  - `continue` returns `action_status = unavailable` when the runtime cannot prepare a resumable thread
  - `retry` and `regenerate` create explicit branches rather than overwriting prior history
- Risks:
  - destructive behavior hidden behind fallback policy
- Done criteria:
  - retry, continue, and regenerate obey the documented lineage model

## P5.3.d
- Title: Lineage replay, reconnect, and closeout hardening
- Status: In progress
- Objective:
  - prove replay fidelity and reconnect stability after lineage-changing actions
- Exact scope:
  - superseded-branch replay
  - reconnect after lineage mutation
  - mixed lineage plus passive/interactive semantics
- Files or modules likely affected:
  - backend integration tests
  - frontend replay/reconnect tests
- Dependencies:
  - `P5.3.a`
  - `P5.3.b`
  - `P5.3.c`
- Implementation notes:
  - validate semantic replay, not only button behavior
  - shared rendering now includes collapsed inline replay groups and `status_block` support for execution transcripts
- Risks:
  - reconnect attaching to the wrong branch
- Done criteria:
  - lineage-changing actions are deterministic after replay and reconnect
