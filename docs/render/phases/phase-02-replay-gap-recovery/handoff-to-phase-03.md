# Phase 02 to Phase 03 Handoff

Status: Ready for execution handoff.

Date: 2026-04-12.

Source phase: `phase-02-replay-gap-recovery` (B02, B03, B05).

Target phase: `phase-03-backend-delta-compaction` (A01, A04, A08).

## 1. Handoff Summary

Phase 02 is marked complete and has locked replay/gap recovery behavior required before backend compaction:

- replay cursor source-of-truth is canonical `event_id`
- reconnect cursor transport supports both `Last-Event-ID` header and `last_event_id` query
- cursor precedence is deterministic (header wins when both are present)
- EventSource reconnect path is app-managed via `last_event_id` query
- replay buffer is active in backend runtime for business events only
- replay miss returns explicit `409 conversation_stream_mismatch` with `replay_miss` semantics
- replay/live boundary overlap is deduped via replay-tail cutoff
- frontend keeps monotonic cursor guard and triggers targeted resync on mismatch

## 2. Contract Guarantees Available to Phase 03

Phase 03 may assume the following are stable:

1. C1 envelope class behavior:
   - replayable business frames carry canonical `event_id`
   - control frames remain non-replayable and non-cursor-affecting
2. C2 replay behavior:
   - replay rule is `event_id > last_event_id`
   - out-of-window cursor recovery is explicit mismatch, not silent continuation
   - replay/live handoff avoids duplicate apply at boundary
3. Frontend recovery policy:
   - reconnect reopens stream with cursor when available
   - targeted snapshot resync path is used for replay mismatch
   - monotonic guard still blocks duplicate/non-monotonic apply
4. Compatibility policy:
   - legacy alias dual-write/fallback remains active during current migration window

## 3. Implemented Components

Backend:

- `backend/conversation/services/thread_replay_buffer_service_v3.py`
- `backend/conversation/services/thread_query_service_v3.py`
- `backend/routes/workflow_v3.py`
- `backend/main.py`
- `backend/errors/app_errors.py`

Frontend:

- `frontend/src/api/client.ts`
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`

Tests:

- `backend/tests/integration/test_chat_v3_api_execution_audit.py`
- `frontend/tests/unit/threadByIdStoreV3.test.ts`
- `frontend/tests/unit/threadEventRouter.test.ts`

## 4. Validation Evidence

Freeze and governance:

- `npm run check:render_freeze` -> pass

Backend replay/stream contract checks:

- `python -m pytest backend/tests/unit/test_thread_query_service_v3.py backend/tests/integration/test_chat_v3_api_execution_audit.py -q`
- result: `32 passed`

Frontend contract consumer checks:

- `npm run typecheck --prefix frontend` -> pass
- `npm run test:unit --prefix frontend -- tests/unit/threadByIdStoreV3.test.ts` -> pass
- targeted replay/router checks: `npx vitest run tests/unit/threadByIdStoreV3.test.ts tests/unit/threadEventRouter.test.ts` -> `16 passed`

## 5. Carry-Over to Phase 03

Out of scope in Phase 02 and expected in Phase 03:

1. Backend delta coalescing window and deterministic compaction rules (A01, A04).
2. No-op lifecycle/event suppression without contract drift (A08).
3. Throughput reduction on hot-path publish/persist while preserving C1/C2 ordering semantics.

## 6. Phase 03 Start Checklist

1. Preserve replay ordering and cursor semantics while introducing compaction.
2. Keep semantic ownership in backend only; frontend must stay presentation-focused.
3. Ensure compaction does not alter terminal lifecycle meaning or turn outcome.
4. Add equivalence tests proving compacted and non-compacted final snapshots match.
5. Keep replay boundary duplicate count at zero after compaction integration.

## 7. Risk Notes for Phase 03

1. Over-compaction can alter semantics if merge rules are too broad.
2. Lifecycle no-op suppression can hide meaningful transitions if guards are incorrect.
3. Micro-batching windows can increase perceived latency if flush boundaries are not explicit.

## 8. Decision Linkage

This handoff remains governed by:

- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/contracts/c1-event-stream-contract-v1.md`
- `docs/render/system-freeze/contracts/c2-replay-resync-contract-v1.md`
- `docs/render/system-freeze/contracts/c3-lifecycle-gating-contract-v1.md`
- `docs/render/system-freeze/contracts/c4-durability-contract-v1.md`
