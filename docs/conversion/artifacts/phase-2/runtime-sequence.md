# Phase 2 Runtime Sequence (V3 Native)

## Scope
- Native runtime/query path for `ThreadQueryServiceV3` + `ThreadRuntimeServiceV3`.
- No V2 back-write on V3 active path.
- Ask legacy transcript mirroring is removed on V3 runtime path.

## Start Turn (Interactive)
1. Route/service calls `ThreadRuntimeServiceV3.start_turn`.
2. Runtime validates access + writable policy.
3. Runtime loads snapshot via `ThreadQueryServiceV3.get_thread_snapshot`.
4. Runtime creates local user item and calls `begin_turn`.
5. `begin_turn` persists:
   - `conversation.item.upsert.v3`
   - `thread.lifecycle.v3` (`running`, `activeTurnId=turn_id`)
6. Background worker streams raw Codex events.
7. Raw events are projected natively by `apply_raw_event_v3` into V3 items/events.
8. Runtime calls `complete_turn` with outcome from turn status.
9. `complete_turn` persists terminal lifecycle (`idle`, `activeTurnId=null`) unless waiting user input.

## Resolve User Input
1. Runtime loads V3 snapshot.
2. Pending request is validated from `uiSignals.activeUserInputRequests`.
3. Runtime marks request `answer_submitted`, patches userInput item.
4. Runtime resolves request upstream (`resolve_runtime_request_user_input`).
5. Runtime applies `apply_resolved_user_input_v3`:
   - request status -> `answered`
   - answers persisted on item + request signal
6. If snapshot was `waiting_user_input` on same turn:
   - lifecycle transitions to `idle` and clears `activeTurnId`.

## Stream Guard
- `ThreadQueryServiceV3.build_stream_snapshot` throws typed `conversation_stream_mismatch`
  when `after_snapshot_version > snapshot.snapshotVersion`.
