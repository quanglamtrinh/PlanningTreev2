# C3 Lifecycle and Gating Contract v1

Status: Frozen state machine contract.

Owner: backend lifecycle producer + frontend queue and UI gating consumer.

## Scope

Defines thread lifecycle states, legal transitions, and how queue/checkpoint logic consumes lifecycle signals.

## Minimum State Set

- `idle`
- `running`
- `waiting_user_input`
- `failed`

## Legal Transition Set (minimum)

- `idle -> running`
- `running -> waiting_user_input`
- `running -> idle`
- `running -> failed`
- `waiting_user_input -> running`
- `waiting_user_input -> idle`
- `waiting_user_input -> failed`

## Contract Consumers

1. Queue gating:
   - queue pause/resume matrix derives from lifecycle state
2. Durability boundaries:
   - checkpoint triggers consume lifecycle terminal and gated boundaries
3. UI status:
   - state badges and controls must match lifecycle source of truth

## Prohibited Behaviors

- implicit lifecycle transitions not represented in stream events
- queue logic using side-channel state outside lifecycle contract
- checkpoint boundary logic diverging from lifecycle contract

