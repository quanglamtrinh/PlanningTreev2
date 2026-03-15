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
- loaded runtime threads
- active streams
- active turns
- runtime request registry
- health state
- project-scoped locks

## Concurrency Rules
- Multiple conversations may stream concurrently.
- Cancelling one stream must not affect another conversation.
- Cross-project isolation is mandatory.
- Stale stream events must be rejected once ownership changes.

## Reconnect And Replay Rules
- Reconnect is keyed by `conversation_id + event_seq + active_stream_id`.
- Reconnect must never bind the UI to the wrong live stream.
- Replay after reload always uses normalized rich messages.
- If reconnect fails, fall back to durable replay plus a fresh runtime session check.

## Persistence Timing Guarantees
- Hot-path forwarding must not wait on durable persistence.
- Durable writes may batch partial deltas.
- Terminal states, lineage transitions, approval requests, runtime input requests, final errors, final usage, and stream ownership transitions must flush promptly.
- Crash recovery reconstructs the last durably written normalized state; very recent unflushed text deltas may be absent.

## Phase 2 Exit Contract
- one execution-thread conversation streams end to end through the new gateway
- same-project session reuse works
- cross-project isolation works
- stale stream events are rejected by ownership rules
- execution reconnect does not re-bind to the wrong stream
- persistence produces replayable normalized conversation records
- hot-path forwarding remains thin
