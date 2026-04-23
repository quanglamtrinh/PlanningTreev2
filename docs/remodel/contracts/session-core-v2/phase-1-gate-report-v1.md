# Session Core V2 Phase 1 Gate Report v1

Date: 2026-04-20  
Status: PASS (Phase 1 complete)

## Scope Implemented

Phase 1 (P1 tối thiểu) delivered:

1. Connection handshake skeleton:
   - `POST /v4/session/initialize`
   - internal `initialized` notification
   - `GET /v4/session/status`
2. Thread lifecycle minimal path:
   - `POST /v4/session/threads/start`
   - `POST /v4/session/threads/{threadId}/resume`
   - `GET /v4/session/threads/list`
   - `GET /v4/session/threads/{threadId}/read`
3. Deterministic pre-handshake guard:
   - non-handshake routes return `ERR_SESSION_NOT_INITIALIZED` + HTTP `409`
4. Phase-gated routes mounted but disabled:
   - deterministic `ERR_PHASE_NOT_ENABLED` + HTTP `501`

## Evidence

Implementation lanes:

- `backend/session_core_v2/transport/stdio_jsonrpc.py`
- `backend/session_core_v2/protocol/client.py`
- `backend/session_core_v2/connection/state_machine.py`
- `backend/session_core_v2/connection/manager.py`
- `backend/session_core_v2/threads/service.py`
- `backend/session_core_v2/storage/runtime_store.py`
- `backend/routes/session_v4.py`
- `backend/main.py` (router/app-state wiring)

Test evidence:

- `backend/tests/unit/test_session_v2_connection_state_machine.py`
- `backend/tests/unit/test_session_v2_protocol_client.py`
- `backend/tests/integration/test_session_v4_api.py`

Run:

- `python -m pytest -q backend/tests/unit/test_session_v2_connection_state_machine.py backend/tests/unit/test_session_v2_protocol_client.py backend/tests/integration/test_session_v4_api.py`
- Result: `7 passed`

## Gate Checklist

1. Handshake contract (`initialize` + internal `initialized`) implemented: PASS
2. Connection state machine transitions enforced: PASS
3. Minimal thread methods (`start/resume/list/read`) implemented: PASS
4. Non-handshake pre-init guard deterministic (`ERR_SESSION_NOT_INITIALIZED`): PASS
5. CamelCase/pass-through payload mapping retained (`clientInfo`, `modelProvider`, `includeTurns`, `sourceKinds`, `modelProviders`): PASS
6. `/v4/session/*` mounted directly, independent of `/v3` prefix: PASS
7. No Session Core V2 dependency on legacy `backend/ai/codex_client.py`: PASS
8. Contract conformance checks for 6 P1 endpoints executed in integration tests: PASS
9. Minimal telemetry logs added (handshake duration, thread RPC latency, handshake failure code): PASS

## Notes and Limits

1. Phase 1 intentionally does not include:
   - `thread/fork`, `thread/loaded/list`, `thread/unsubscribe`
   - turn runtime (`turn/start|steer|interrupt`)
   - server request resolution flows
2. Runtime store is authoritative in backend for P1 process lifetime (in-memory baseline), with journal capture for thread-level notifications:
   - `thread/started`
   - `thread/status/changed`
   - `thread/closed`
   - `error`

## Decision

Phase 1 gate passes.  
Session Core V2 is ready to proceed to Phase 2 (turn runtime).
