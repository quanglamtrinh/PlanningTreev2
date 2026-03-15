# Validation Checklist

## Build And Boot Checks
- backend boots with the new conversation foundation files present
- frontend builds with the new conversation types and store
- breadcrumb navigation is unaffected

## Embedding Checks
- execution embedding works when Phase 3 starts
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
- send-start creates one stable assistant placeholder message and one stable empty `assistant_text` part
- send-start emits exactly two `message_created` events with `event_seq = n + 1` then `n + 2`
- success path emits `assistant_text_final` before `completion_status(completed)`
- error, interrupted, and cancelled paths emit terminal `completion_status(...)` without `assistant_text_final`
- stream ownership reads and writes happen under the project session lock
- non-execution-eligible send returns the correct 4xx and does not create active stream ownership
- gateway shutdown flushes terminal and other high-value writes before session-manager shutdown

## PlanningTree Wrapper Regression Checks
- ask packet sidecar behavior remains intact
- planning split wrappers remain intact
- execution framing remains intact
- task, brief, and spec remain read-only context
- chat does not write back into breadcrumb artifacts in this migration phase
