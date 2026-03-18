# Gateway And Session Architecture

## Thin Gateway Responsibilities
- Resolve canonical conversation identity.
- Resolve or create the conversation record.
- Reject non-execution-eligible sends before ownership or durable mutation.
- Build request context before each turn.
- Acquire the correct project-scoped session.
- Bind active `stream_id` and `turn_id` under the project session lock.
- Allocate `event_seq` in the gateway under the project session lock.
- Forward stream events immediately.
- Normalize and persist in parallel.
- Expose only the Phase 2.2 command surface:
  - `GET` execution conversation
  - `POST` execution send
  - `GET` execution events

## Phase 2 Scope
- Phase 2 remains backend-only and execution-only.
- `P2.1` introduces the project-scoped session manager skeleton only.
- `P2.2` introduces only the execution-scoped conversation-v2 `get`, `send`, and `events` route surface in parallel to legacy routes.
- Ask and planning v2 routes are out of scope for Phase 2.
- No UI cutover or ChatPanel replacement is part of Phase 2.

## Request Setup Path
- Load project metadata.
- Load node metadata.
- Resolve `thread_type`.
- Resolve `runtime_mode`.
- Load task, brief, and spec context.
- Resolve the canonical execution conversation.
- Allocate `turn_id`, `stream_id`, stable user `message_id`, stable assistant placeholder `message_id`, and stable `assistant_text` `part_id`.
- Resolve or reuse `app_server_thread_id` when already durably bound.
- Create two `message_created` events synchronously at send-start:
  - user `message_created` gets `event_seq = n + 1`
  - assistant placeholder `message_created` gets `event_seq = n + 2`
- Persist setup-path state synchronously before the background runtime turn starts.

## Hot Stream Path
- Forward events to the UI as quickly and as raw as practical.
- Stamp `conversation_id`, `stream_id`, and gateway-allocated `event_seq`.
- Reject stale stream mutations.
- Avoid whole-conversation recompute on every delta.
- Persist normalized updates in parallel.

## Canonical Identity And Ownership
- One canonical `conversation_id` per `(project_id, node_id, thread_type)` in this migration phase.
- `app_server_thread_id` is runtime state bound to that conversation.
- Stream ownership is always `(conversation_id, stream_id)`.
- One active stream owner per conversation.

## Session Pool Design
- Pool sessions by `project_id`.
- One persistent `codex-app-server` session per project or workspace scope.
- Multiple ask, planning, and execution conversations in one project may share the session.
- Different projects must never share a session.
- A same-project request with a conflicting `workspace_root` must be rejected, not silently reused.
- Conflict detection should compare normalized workspace-root keys using path normalization rules rather than raw strings.

## Session Manager State
- `loaded_runtime_threads: dict[str, RuntimeThreadState]`
- `active_streams: dict[str, str]` keyed by `conversation_id`
- `active_turns: dict[str, str]` keyed by `conversation_id`
- `runtime_request_registry: dict[str, dict[str, Any]]`
- `health`
- project-scoped `RLock`

## Session Health Vocabulary
- `idle` for an existing session whose client is present but not currently alive
- `ready` for an existing session whose client reports `client_alive=True`
- `error` when client status inspection fails
- `missing` for unknown sessions returned by manager lookup
- `stopped` only on a held session object after reset or shutdown teardown

## RuntimeThreadState
- `thread_id`
- `last_used_at`
- `active_turn_id`
- `status`

## Ownership And Locking Rules
- All reads and writes for `active_streams`, `active_turns`, and `loaded_runtime_threads` must happen under the project session lock.
- Ownership checking lives in `ConversationGateway`, not in routes and not in the broker.
- Ownership checks on streaming callbacks must read the current owner under the same lock.
- `event_seq` allocation must happen under the same lock after ownership is confirmed and before the event is published.
- No callback may mutate conversation state based on an unlocked partial snapshot of ownership.
- Stale callbacks must not publish, persist, or clear ownership.
- Terminal cleanup may clear ownership only if the finishing callback still owns both `stream_id` and `turn_id`.
- Reset and shutdown teardown must explicitly clear `active_streams`, `active_turns`, and `runtime_request_registry`.
- Reset and shutdown teardown must leave loaded runtime threads in a non-active state by clearing `active_turn_id`, marking status as `stopped`, and refreshing `last_used_at`.

## Concurrency Rules
- Multiple conversations may stream concurrently.
- Cancelling one stream must not affect another conversation.
- Cross-project isolation is mandatory.
- Stale stream events must be rejected once ownership changes.
- Infrastructure-level concurrency remains supported within a project session.
- Execution-specific single-active orchestration is enforced separately per execution conversation and does not change the session reuse model.

## Reconnect And Replay Rules
- Reconnect is keyed by `conversation_id + event_seq + active_stream_id`.
- Reconnect must never bind the UI to the wrong live stream.
- Replay after reload always uses normalized rich messages.
- If reconnect fails, fall back to durable replay plus a fresh runtime session check.
- Execution snapshot reads are durable-store-first and may enrich with live ownership metadata if a project session is active.
- Snapshot enrichment is limited to live ownership and cursor metadata only; it must not synthesize transcript content from broker or session memory.
- If SSE reconnect supplies `expected_stream_id` and it does not match current ownership, the gateway must return structured `409` instead of binding to the wrong stream.

## Persistence Timing Guarantees
- Hot-path forwarding must not wait on durable persistence.
- Durable writes may batch partial deltas.
- Terminal states, lineage transitions, approval requests, runtime input requests, final errors, final usage, and stream ownership transitions must flush promptly.
- Crash recovery reconstructs the last durably written normalized state; very recent unflushed text deltas may be absent.
- Setup-path writes may be synchronous.
- `ConversationStore` must expose a grouped mutation path that can atomically update:
  - `record.status`
  - `record.current_runtime_mode`
  - `record.active_stream_id`
  - `record.app_server_thread_id`
  - `record.event_seq`
  - `record.updated_at`
  - related message and part mutations for the same persistence task
- Delta writes should go through a queue or worker.
- The queue must flush promptly on completion, interruption, cancellation, or final error.
- Active stream ownership changes and `app_server_thread_id` bindings are high-value writes and must be prioritized for durable flush.
- On terminal success or error, the gateway must finish terminal persistence before ownership is considered fully cleared for that `conversation_id`.
- The gateway-owned worker must expose `flush_and_stop()`.
- App shutdown must wait for terminal and other high-value gateway writes before `codex_session_manager.shutdown()`.

## Phase 2 Execution Path Defaults
- `GET /v2/projects/{project_id}/nodes/{node_id}/conversations/execution` resolves or lazily creates the canonical execution conversation and returns a durable-store-first snapshot.
- `POST /v2/projects/{project_id}/nodes/{node_id}/conversations/execution/send` is execution-only and must reject non-execution-eligible nodes.
- Send-start creates one stable user message, one stable assistant placeholder message, and one stable empty `assistant_text` part for the turn.
- All assistant deltas and final text updates for that turn target the same placeholder message and part.
- The Phase 2 event surface remains minimal:
  - `message_created`
  - `assistant_text_delta`
  - `assistant_text_final`
  - `completion_status`
- `assistant_text_final` exists only on the successful path and must be emitted before `completion_status(completed)`.
- Error, interrupted, and cancelled paths emit terminal `completion_status(...)` without `assistant_text_final`.
- `completion_status` is terminal-only in Phase 2 with statuses:
  - `completed`
  - `error`
  - `interrupted`
  - `cancelled`

## Phase 2 Exit Contract
- one execution-thread conversation streams end to end through the new gateway
- same-project session reuse works
- cross-project isolation works
- success-path event order is explicitly proven:
  - `message_created(user)`
  - `message_created(assistant)`
  - zero or more `assistant_text_delta`
  - `assistant_text_final`
  - `completion_status(completed)`
- stale stream events are rejected by ownership rules
- execution reconnect does not re-bind to the wrong stream
- persistence produces replayable normalized conversation records
- durable-store-first snapshot reads are explicitly proven to enrich only `active_stream_id` and `event_seq`, not transcript content
- terminal flush and shutdown flush ordering are explicitly proven by tests
- hot-path forwarding remains thin
