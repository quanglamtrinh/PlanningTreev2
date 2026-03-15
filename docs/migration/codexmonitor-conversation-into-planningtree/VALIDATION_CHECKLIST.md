# Validation Checklist

## Build And Boot Checks
- backend boots with the new conversation foundation files present
- frontend builds with the new conversation types and store
- breadcrumb navigation is unaffected

## Embedding Checks
- execution visible embedding works when Phase 3.3 completes
- ask embedding works when Phase 4 starts
- planning embedding works when Phase 4 starts
- PlanningTree wrappers remain intact

## Latency Sanity Checks
- first visible event appears well before full turn completion
- no whole-thread recompute occurs on every assistant delta
- incremental streaming remains visible under normal use

## Dense-Event Stress Checks
- reasoning-heavy streams do not freeze scrolling
- tool-heavy streams do not stall rendering
- diff and status bursts remain usable

## Concurrent Stream Checks
- two conversations in one project can stream concurrently
- different projects remain isolated
- one cancel does not cross-cancel another conversation
- stale stream events are rejected after stream ownership changes
- execution-specific single-active orchestration does not disable same-project session reuse

## Replay Fidelity Checks
- reload reconstructs the same rich conversation UI from normalized messages
- superseded and regenerated lineage remains visible
- approval, runtime input, tool, and status states replay correctly

## Reconnect Correctness Checks
- reconnect uses `conversation_id + event_seq + active_stream_id`
- reconnect never attaches to the wrong live stream
- reconnect failure falls back to durable replay plus runtime state check
- stale `expected_stream_id` reconnect returns structured `409`

## Phase 2 Gateway Checks
- execution-only v2 `get`, `send`, and `events` routes exist in parallel to legacy routes
- `GET` execution snapshot is durable-store-first and not synthesized from in-memory-only events
- `GET -> POST send -> GET again` keeps the same canonical `conversation_id`
- memory-only live assistant text must not appear in `GET` execution snapshots
- live enrichment is limited to `record.active_stream_id` and `record.event_seq`
- send-start creates one stable assistant placeholder message and one stable empty `assistant_text` part
- send-start emits exactly two `message_created` events with `event_seq = n + 1` then `n + 2`
- success-path events keep a shared `conversation_id` and `stream_id`
- success-path `event_seq` values are strictly monotonic
- assistant deltas and final updates target the same stable assistant `message_id` and `part_id`
- success path emits `assistant_text_final` before `completion_status(completed)`
- error, interrupted, and cancelled paths emit terminal `completion_status(...)` without `assistant_text_final`
- stream ownership reads and writes happen under the project session lock
- non-execution-eligible send returns the correct 4xx and does not create active stream ownership
- terminal success keeps ownership until terminal persistence finishes
- gateway `flush_and_stop()` does not drop queued terminal persistence work
- gateway shutdown flushes terminal and other high-value writes before session-manager shutdown

## Phase 3 Tracking Checks
### Phase 3.1 - Execution Conversation Data Plumbing
- snapshot load works against the execution v2 `GET`
- SSE subscribe works against the execution v2 `events` path
- reconnect re-GET plus SSE resubscribe behavior works for execution
- send path is wired through the execution v2 `POST`
- keyed frontend execution conversation state updates correctly
- no visible execution transcript cutover occurs yet

### Phase 3.2 - Shared Conversation Surface Presentation
- user messages render in the shared surface
- assistant messages render in the shared surface
- streaming assistant text renders correctly
- loading, error, and empty states render correctly
- unsupported rich parts degrade safely instead of breaking rendering
- the visible execution transcript is still not switched by this phase alone

### Phase 3.3 - Execution Tab Visible Cutover
- the visible execution transcript switches to the shared conversation surface
- execution framing remains intact inside `BreadcrumbWorkspace`
- visible composer and send path work through the execution v2 backend
- reload and reconnect work correctly inside the execution tab
- rollback remains available during the cutover window
- Phase 3 is not considered complete until this phase is complete

## PlanningTree Wrapper Regression Checks
- ask packet sidecar behavior remains intact
- planning split wrappers remain intact
- execution framing remains intact
- task, brief, and spec remain read-only context
- chat does not write back into breadcrumb artifacts in this migration phase
