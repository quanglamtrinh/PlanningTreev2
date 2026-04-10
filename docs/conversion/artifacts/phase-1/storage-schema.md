# Phase 1 Storage Schema Notes

Date: 2026-04-10  
Owner: PTM Core Team  
Status: completed (phase-1 closeout artifact)

## 1. Canonical V3 snapshot store

- Store module: `backend/conversation/storage/thread_snapshot_store_v3.py`
- Canonical path:
  - `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- Thread role file key uses canonical role values:
  - `ask_planning | execution | audit`

## 2. Canonical payload shape (domain/store)

Thread snapshot payload persisted by V3 store uses:

- `projectId`
- `nodeId`
- `threadRole`
- `threadId`
- `activeTurnId`
- `processingState`
- `snapshotVersion`
- `createdAt`
- `updatedAt`
- `items`
- `uiSignals`

`uiSignals` contains:

- `planReady`
- `activeUserInputRequests`

## 3. Compatibility normalization rules

- Read compatibility accepts legacy role fields:
  - `threadRole` (preferred)
  - `thread_role` (input compatibility)
  - `lane` (input compatibility only)
- `lane` values are mapped to canonical `threadRole`:
  - `ask -> ask_planning`
  - `execution -> execution`
  - `audit -> audit`
- Persisted canonical payload does not store legacy `lane`.

Additional normalization:

- Invalid/missing `processingState` falls back to `idle`.
- `snapshotVersion` is coerced to non-negative integer.
- `planReady` and `activeUserInputRequests` are normalized to deterministic shapes.
- `items` are normalized and deterministically ordered by `(sequence, id)`.

## 4. Phase boundaries

- Phase 1 is foundation-only:
  - adds domain/store canonicalization and V3 store wiring
  - does not change active `/v3` route output behavior
- Route/event contract tightening is deferred by plan sequence:
  - Phase 3: threadRole-primary native `/v3` route output
  - Phase 5: frontend active-path lane-read removal
  - Phase 7: hard cleanup of lane emission/type/test compatibility
