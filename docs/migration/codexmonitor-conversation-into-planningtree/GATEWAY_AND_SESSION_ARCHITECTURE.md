# Gateway And Session Architecture

## Thin Gateway Responsibilities
- Resolve canonical conversation identity.
- Resolve or create the conversation record.
- Build request context before each turn.
- Acquire the correct project-scoped session.
- Bind active `stream_id`.
- Forward stream events immediately.
- Normalize and persist in parallel.
- Expose command surface:
  - `send`
  - `cancel`
  - `retry`
  - `continue`
  - `regenerate`
  - `respond_to_server_request`
  - load and stream endpoints

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
- Resolve tool policy and approval policy.
- Resolve or resume `app_server_thread_id`.
- Create `stream_id`.
- Record lineage intent before streaming begins.

## Hot Stream Path
- Forward events to the UI as quickly and as raw as practical.
- Stamp `conversation_id`, `stream_id`, and `event_seq`.
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

## Session Manager State
- `loaded_runtime_threads: dict[str, RuntimeThreadState]`
- `active_streams: dict[str, str]` keyed by `conversation_id`
- `active_turns: dict[str, str]` keyed by `conversation_id`
- `runtime_request_registry: dict[str, dict[str, Any]]`
- `health`
- project-scoped `RLock`

## RuntimeThreadState
- `thread_id`
- `last_used_at`
- `active_turn_id`
- `status`

## Ownership And Locking Rules
- All reads and writes for `active_streams`, `active_turns`, and `loaded_runtime_threads` must happen under the project session lock.
- Ownership checks on streaming callbacks must read the current owner under the same lock.
- No callback may mutate conversation state based on an unlocked partial snapshot of ownership.

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
- If SSE reconnect supplies `expected_stream_id` and it does not match current ownership, the gateway must return structured `409` instead of binding to the wrong stream.

## Persistence Timing Guarantees
- Hot-path forwarding must not wait on durable persistence.
- Durable writes may batch partial deltas.
- Terminal states, lineage transitions, approval requests, runtime input requests, final errors, final usage, and stream ownership transitions must flush promptly.
- Crash recovery reconstructs the last durably written normalized state; very recent unflushed text deltas may be absent.
- Setup-path writes may be synchronous.
- Delta writes should go through a queue or worker.
- The queue must flush promptly on completion, interruption, cancellation, or final error.
- Active stream ownership changes and `app_server_thread_id` bindings are high-value writes and must be prioritized for durable flush.

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
- `completion_status` is terminal-only in Phase 2 with statuses:
  - `completed`
  - `error`
  - `interrupted`
  - `cancelled`

## Phase 2 Exit Contract
- one execution-thread conversation streams end to end through the new gateway
- same-project session reuse works
- cross-project isolation works
- stale stream events are rejected by ownership rules
- execution reconnect does not re-bind to the wrong stream
- persistence produces replayable normalized conversation records
- hot-path forwarding remains thin
