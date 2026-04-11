# Phase 2 Event Contract (V3)

## Envelope
All persisted events are published through `build_thread_envelope` with:
- `channel=thread`
- `projectId`
- `nodeId`
- `threadRole` (canonical)
- `snapshotVersion`
- `type`
- `payload`

## Event Types Used by V3 Runtime/Query
- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `thread.lifecycle.v3`
- `conversation.ui.plan_ready.v3`
- `conversation.ui.user_input.v3`
- `thread.error.v3`

## Mutation Rules
- `persist_thread_mutation` always increments `snapshotVersion`.
- `thread.snapshot.v3` payload is always authoritative snapshot payload from persisted V3 store.
- Plan/UI signal events are emitted from V3 projector refresh logic (no V2 adapter on native path).

## User Input Signal Contract
- Source of truth: `snapshot.uiSignals.activeUserInputRequests`.
- State progression:
  - `requested`
  - `answer_submitted`
  - `answered` (or `stale` on runtime-missing reconciliation)

## Reset Contract
- `reset_thread` emits canonical reset snapshot via `thread.snapshot.v3`.
- Ask-only reset policy remains enforced above runtime/query layer (route/service policy layer).
