# S6 Idempotency Contract v1

Status: Normative

## Scope

Defines idempotency rules that remain in PlanningTree after adopting Codex
app-server semantics below `threadId`.

## Keys

1. `resolutionKey` (required):
   - `requests/{requestId}/resolve`
   - `requests/{requestId}/reject`
2. Workflow `idempotencyKey` (required by workflow APIs):
   - `projectId + nodeId + role -> threadId` binding creation/adoption
   - workflow business mutations
   - workflow context refresh/rebase decisions

`turn/start`, `turn/steer`, `turn/interrupt`, and `thread/inject_items` do not
accept PlanningTree `clientActionId` fields. Retries at those methods follow
Codex app-server behavior.

## Deterministic behaviors

1. Duplicate key + identical payload:
   - return previously accepted result
   - no duplicate side effects
2. Duplicate key + different payload:
   - reject with `ERR_IDEMPOTENCY_PAYLOAD_MISMATCH`
3. Resolve/reject for stale/terminal request:
   - reject with `ERR_REQUEST_STALE`
4. Illegal turn mutation on terminal turn:
   - reject with `ERR_TURN_TERMINAL` (or `ERR_TURN_NOT_STEERABLE` for steer precondition)

## Storage

Idempotency records are persisted and tied to journal state:

1. `idempotencyKey`
2. action type
3. payload hash
4. accepted response hash
5. related `threadId`, `turnId`, `requestId`
6. `acceptedAtMs`
7. `journalEventSeq` anchor (when applicable)

## Replay/reconnect rule

Duplicate behavior must remain stable across reconnect and process restart.
Idempotency result cannot depend on in-memory-only cache.

## TTL policy

Retention for idempotency records must be >= journal retention floor for the same thread scope.
Never expire idempotency records earlier than replay window for active canary/cutover periods.

