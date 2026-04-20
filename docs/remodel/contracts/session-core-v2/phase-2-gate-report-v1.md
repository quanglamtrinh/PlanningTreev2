# Session Core V2 Phase 2 Gate Report v1

Date: 2026-04-20  
Status: PASS (Phase 2 complete)

## Scope Implemented

Phase 2 delivered:

1. Turn runtime APIs enabled:
   - `POST /v4/session/threads/{threadId}/turns/start`
   - `POST /v4/session/threads/{threadId}/turns/{turnId}/steer`
   - `POST /v4/session/threads/{threadId}/turns/{turnId}/interrupt`
2. Event stream API enabled:
   - `GET /v4/session/threads/{threadId}/events`
3. Turn state machine enforcement (`S7`) for legal/illegal transitions.
4. Idempotency behavior (`S6`) for turn mutations using `clientActionId`.
5. Journal-first replay/cursor behavior (`S5`) with deterministic:
    - `ERR_CURSOR_INVALID`
    - `ERR_CURSOR_EXPIRED`
6. Backpressure behavior via bounded subscriber queue and lagged reset, with Tier-0 durability through journal/replay.
7. Runtime flags wired:
    - `SESSION_CORE_V2_ENABLE_TURNS`
    - `SESSION_CORE_V2_ENABLE_EVENTS`
8. Durability hardening:
   - snapshot payload persisted with `thread`, `turnIndex`, `itemIndex`, `pendingRequestIndex`
   - snapshot cadence enforced by `200` Tier-0 events or `10s`
   - retention dual-floor enforced (`7 days` + `200000 events/thread`, whichever larger)
9. API hygiene:
   - removed non-contract public `maxEvents` query behavior from events endpoint

## Evidence

Implementation lanes:

- `backend/session_core_v2/protocol/client.py`
- `backend/session_core_v2/turns/service.py`
- `backend/session_core_v2/connection/manager.py`
- `backend/session_core_v2/storage/runtime_store.py`
- `backend/routes/session_v4.py`
- `backend/config/app_config.py`
- `backend/main.py`

Test evidence:

- `backend/tests/unit/test_session_v2_protocol_client.py`
- `backend/tests/unit/test_session_v2_turn_state_machine.py`
- `backend/tests/unit/test_session_v2_runtime_store.py`
- `backend/tests/unit/test_session_v2_idempotency.py`
- `backend/tests/integration/test_session_v4_api.py`

Run:

- `python -m pytest -q backend/tests/unit/test_session_v2_connection_state_machine.py backend/tests/unit/test_session_v2_protocol_client.py backend/tests/unit/test_session_v2_turn_state_machine.py backend/tests/unit/test_session_v2_runtime_store.py backend/tests/unit/test_session_v2_idempotency.py backend/tests/integration/test_session_v4_api.py`
- Result: `19 passed`
- `python -m pytest -q backend/tests/integration/test_chat_api.py -k "not long and not slow"` -> `18 passed`
- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py -k "test_v3_execution_snapshot_by_id_returns_wrapped_snapshot or test_v3_ask_snapshot_by_id_returns_wrapped_snapshot or test_v3_workflow_state_endpoint_calls_canonical_service"` -> `3 passed`

## Gate Checklist

1. Turn APIs and events endpoint enabled: PASS
2. Deterministic idempotency behaviors for duplicate/retry: PASS
3. Deterministic turn legality errors (`ERR_ACTIVE_TURN_MISMATCH`, `ERR_TURN_NOT_STEERABLE`, `ERR_TURN_TERMINAL`): PASS
4. Replay cursor validation + expiry semantics (`ERR_CURSOR_INVALID`, `ERR_CURSOR_EXPIRED` + `snapshotPointer` details): PASS
5. Journal-first event ingest and replay ordering: PASS
6. Bounded queue and lagged reset behavior without producer stall: PASS
7. Feature flags gate/rollback behavior for turns/events: PASS
8. Non-P2 endpoints remain phase-gated: PASS
9. Snapshot payload + cadence + retention dual-floor hardening: PASS
10. `/v3` regression checks: PASS

## Decision

Phase 2 gate passes.  
Session Core V2 is ready to proceed to Phase 3 (server-request lifecycle).
