# Ask Queue Gating Matrix v1

Status: Frozen for ask migration.

## Send Window Open (all must be true)

1. Active lane is ask_planning.
2. Snapshot exists.
3. activeTurnId == null.
4. processingState == idle.
5. No pending required user input request.

## Send Window Closed (any true)

1. Active turn running.
2. waiting_user_input active.
3. Stream or state mismatch requiring reload.
