# S7 Turn State Machine Contract v1

Status: Normative

## States

1. `idle`
2. `inProgress`
3. `waitingUserInput`
4. `completed` (terminal)
5. `failed` (terminal)
6. `interrupted` (terminal)

## Allowed transitions

1. `notCreated -> idle` via accepted `turn/start`
2. `idle -> inProgress` on first runtime item/event
3. `inProgress -> inProgress` via accepted `turn/steer`
4. `inProgress -> waitingUserInput` when server request is emitted
5. `waitingUserInput -> inProgress` via valid resolve/reject continuation
6. `inProgress -> completed|failed` via terminal completion
7. `inProgress|waitingUserInput -> interrupted` via valid `turn/interrupt`

No other transitions are legal.

## Request legality matrix

1. `turn/steer`:
   - legal only when state is `inProgress`
   - requires `expectedTurnId` equals active turn id
2. `turn/interrupt`:
   - legal when state is `inProgress` or `waitingUserInput`
3. `resolve/reject`:
   - legal only for pending request attached to `waitingUserInput` or active runtime continuation context
4. Any mutation in terminal state:
   - deterministic failure

## Deterministic errors

1. `ERR_TURN_NOT_STEERABLE`
2. `ERR_TURN_TERMINAL`
3. `ERR_REQUEST_STALE`
4. `ERR_ACTIVE_TURN_MISMATCH`

## Terminal invariants

1. Terminal states are immutable.
2. `completedAtMs` must be set for terminal states.
3. A turn has exactly one terminal event (`turn/completed` with status).
4. After terminal transition, no further item delta events for that turn are valid.

