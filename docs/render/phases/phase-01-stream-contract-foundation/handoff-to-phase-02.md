# Phase 01 to Phase 02 Handoff

Status: Ready for execution handoff.

Date: 2026-04-12.

Source phase: `phase-01-stream-contract-foundation` (B01, B04, B06).

Target phase: `phase-02-replay-gap-recovery` (B02, B03, B05).

## 1. Handoff Summary

Phase 01 is marked complete and has locked the stream contract foundation needed by Phase 02:

- canonical C1 business envelope is active
- replayable business events emit SSE `id` aligned to canonical `event_id`
- `event_id` issuance is monotonic and durable per thread
- heartbeat and `stream_open` are separated from replay cursor semantics
- frontend consumer enforces canonical-first parsing and controlled fallback behavior

## 2. Contract Guarantees Available to Phase 02

Phase 02 may assume the following are stable:

1. Replayable business envelope shape:
   - `schema_version`
   - `event_id`
   - `event_type`
   - `thread_id`
   - `turn_id`
   - `snapshot_version`
   - `occurred_at_ms`
   - `payload`
2. Legacy compatibility during migration window:
   - producer dual-write is active (canonical + legacy aliases)
   - consumer is canonical-first with legacy fallback
3. Cursor correctness rules:
   - only validated replayable business events advance `lastEventId`
   - heartbeat does not affect cursor
   - `stream_open` does not affect cursor
   - replay cursor transport supports both `Last-Event-ID` header and `last_event_id` query
   - when both cursor transports are present, header takes precedence

## 3. Implemented Components

Backend:

- `backend/conversation/domain/events.py`
- `backend/conversation/domain/types.py`
- `backend/conversation/services/thread_registry_service.py`
- `backend/conversation/services/thread_query_service_v3.py`
- `backend/routes/workflow_v3.py`

Frontend:

- `frontend/src/features/conversation/state/threadEventRouter.ts`
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`

Phase artifacts:

- `docs/render/phases/phase-01-stream-contract-foundation/subphases/subphase-01-stream-contract-foundation-implementation.md`

## 4. Validation Evidence

Preflight:

- `npm run check:render_freeze` -> pass

Backend stream-contract tests:

- `python -m pytest backend/tests/unit/test_thread_query_service_v3.py backend/tests/integration/test_chat_v3_api_execution_audit.py -q`
- result: `32 passed`

Frontend parser/store tests:

- `npm run typecheck --prefix frontend`
- `npm run test:unit --prefix frontend -- tests/unit/threadByIdStoreV3.test.ts`
- result: pass

## 5. Carry-Over to Phase 02

Out of scope in Phase 01 and expected in Phase 02:

1. Full selective replay by reconnect cursor (`event_id` semantics end-to-end with header/query transport precedence).
2. Replay buffer retention window and eviction policy.
3. Explicit `replay_miss` flow and targeted resync boundary behavior.
4. Replay/live overlap dedupe at reconnect boundary.

## 6. Phase 02 Start Checklist

1. Keep C1 envelope unchanged while adding replay behavior.
2. Use canonical `event_id` as the only replay ordering key.
3. Ensure replay path includes only replayable business events.
4. Keep heartbeat and `stream_open` non-replayable and non-cursor-affecting.
5. Preserve legacy compatibility policy until C1 cutover completion is explicitly approved.

## 7. Risk Notes for Phase 02

1. Replay buffer must not introduce duplicate apply at boundary handoff.
2. Any reconnect optimization must preserve current hard-error behavior for invalid envelopes.
3. Do not reintroduce snapshot-version-only reconnect coupling as primary recovery mechanism.

## 8. Decision Linkage

This handoff remains governed by:

- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/contracts/c1-event-stream-contract-v1.md`
- `docs/render/system-freeze/contracts/c2-replay-resync-contract-v1.md`
- `docs/render/system-freeze/contracts/c1-event-stream-bridge-policy-v1.md`
