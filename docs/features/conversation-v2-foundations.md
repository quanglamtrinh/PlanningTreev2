# Conversation V2 Foundations

## Current Behavior
- PlanningTree currently manages ask and execution chat state with separate singleton stores.
- Conversation persistence is too flat for rich replay.
- There is no shared conversation identity model or dedicated gateway path yet.

## Desired Behavior
- Introduce a shared conversation contract layer that supports:
  - canonical conversation identity
  - runtime mode separation
  - normalized rich messages
  - keyed frontend conversation state
  - dedicated backend persistence contracts
- Keep current visible UI flows in place while these foundations are added.

## Domain Rules
- One canonical `conversation_id` per `(project_id, node_id, thread_type)` in this migration phase.
- `thread_type` and `runtime_mode` are separate concepts.
- Normalized rich messages are the durable truth model.
- Replay rebuilds from normalized messages, not raw event logs.

## API Changes
- No user-facing route cutover in this batch.
- New contracts are additive and prepare Phase 2 gateway work.

## Acceptance Criteria
- Backend and frontend contracts compile.
- Keyed conversation state exists independently of singleton chat and ask stores.
- Dedicated backend conversation persistence scaffolding exists.

## Test Plan
- backend unit tests for the conversation store
- frontend unit tests for keyed store merge behavior
- frontend build verification
