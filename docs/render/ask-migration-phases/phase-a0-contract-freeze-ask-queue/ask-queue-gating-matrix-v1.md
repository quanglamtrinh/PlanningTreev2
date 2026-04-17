# Ask Queue Gating Matrix v1

Status: Frozen for ask migration.

Last updated: 2026-04-14.

## 1. Send Window Open (all must be true)

1. Active lane is `ask_planning`.
2. Snapshot exists.
3. `activeTurnId == null`.
4. `processingState == idle`.
5. No pending required user-input request with status in:
   - `requested`
   - `answer_submitted`

## 2. Blocked Reason Set (Frozen)

Exactly one primary blocked reason must be emitted when send window is closed.

Allowed reasons:

1. `snapshot_unavailable`
2. `stream_or_state_mismatch`
3. `active_turn_running`
4. `waiting_user_input`
5. `operator_pause`

No additional ask blocked reason codes are allowed in A1-A3.

## 3. Deterministic Evaluation Order

When evaluating paused state, apply this order:

1. if snapshot missing -> `snapshot_unavailable`
2. if stream/state mismatch recovery is required -> `stream_or_state_mismatch`
3. if operator pause enabled -> `operator_pause`
4. if `activeTurnId != null` or `processingState != idle` -> `active_turn_running`
5. if pending required user-input exists -> `waiting_user_input`
6. otherwise -> send window open

## 4. Contract Notes

1. Ask send-window evaluation must be deterministic for the same snapshot + queue state.
2. This matrix is ask-lane specific and must not alter execution queue gating behavior.

