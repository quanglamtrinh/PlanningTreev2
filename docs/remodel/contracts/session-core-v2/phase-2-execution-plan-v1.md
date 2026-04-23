# Session Core V2 Phase 2 Execution Plan v1

Date: 2026-04-20  
Status: Implemented (hardening patch applied)  
Depends on: `phase-1-gate-report-v1.md` (PASS), contracts `S0..S8` (Frozen v1)

## 1. Goal

Ship Phase 2 (`Turn Runtime`) theo Codex-native semantics, giữ boundary sạch:

1. enable `turn/start`, `turn/steer`, `turn/interrupt` trên `/v4/session/*`
2. stream event canonical theo `Thread / Turn / Item`
3. enforce đầy đủ `S6` idempotency + `S7` turn state machine
4. giữ Phase 1 thread APIs ổn định, không kéo business logic ask/audit/execution vào core

## 2. Codex parity anchors (must-follow)

Implementation P2 phải bám sát các nguồn chuẩn sau:

1. `C:/Users/Thong/codex/codex-rs/app-server-protocol/src/protocol/v2.rs`
   - `TurnStartParams`, `TurnSteerParams`, `TurnInterruptParams`
   - `ThreadStatusChangedNotification`, `TurnCompletedNotification`
   - `ItemStartedNotification`, `ItemCompletedNotification`, `AgentMessageDeltaNotification`
2. `C:/Users/Thong/codex/codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json`
   - method/notification names và field naming camelCase
3. `C:/Users/Thong/codex/codex-rs/app-server-client/src/lib.rs`
   - bounded queue, overload behavior, lagged signaling
   - lossless delivery set for transcript/completion tier
4. `C:/Users/Thong/codex/sdk/python/src/codex_app_server/client.py`
   - request mapping shape cho `initialize`, `turn_start`, `turn_steer`, `turn_interrupt`
5. `C:/Users/Thong/codex/sdk/python/src/codex_app_server/generated/notification_registry.py`
   - canonical notification registry names

## 3. Scope

## 3.1 In scope (P2)

1. Backend turn runtime API enable:
   - `POST /v4/session/threads/{threadId}/turns/start`
   - `POST /v4/session/threads/{threadId}/turns/{turnId}/steer`
   - `POST /v4/session/threads/{threadId}/turns/{turnId}/interrupt`
2. Backend event stream API enable:
   - `GET /v4/session/threads/{threadId}/events` (SSE, cursor-aware)
3. Notification ingest expansion:
   - ingest turn/item delta + completion notifications into journal
4. Turn state machine enforcement theo `S7`
5. Idempotency enforcement theo `S6`
6. Replay/cursor behavior theo `S5` cho stream consumers
7. Test suite mở rộng (unit + integration + contract conformance)

## 3.2 Out of scope (still phase-gated)

1. `requests/pending|resolve|reject` full lifecycle (Phase 3)
2. approval UX, request_user_input UI flows (Phase 3/4)
3. ask/execution/audit specialization (post-core layer)
4. frontend Session Console V2 hoàn chỉnh (Phase 4)

## 4. Work breakdown

## 4.1 W1 - Protocol client extensions (thin adapter only)

Files:

1. `backend/session_core_v2/protocol/client.py`
2. `backend/tests/unit/test_session_v2_protocol_client.py`

Tasks:

1. add thin methods:
   - `turn_start(thread_id, payload)`
   - `turn_steer(thread_id, payload)` with required `expectedTurnId`
   - `turn_interrupt(thread_id, turn_id)`
2. preserve camelCase passthrough (`clientActionId`, `expectedTurnId`, etc.)
3. keep `initialized` internal transition behavior unchanged

Acceptance:

1. method mapping test pass
2. request payload keys unchanged from OpenAPI contract

## 4.2 W2 - Turn service + state machine enforcement

Files:

1. add `backend/session_core_v2/turns/service.py`
2. add `backend/session_core_v2/turns/state_machine.py` (or equivalent in service layer)
3. update `backend/session_core_v2/connection/manager.py`

Tasks:

1. implement turn start/steer/interrupt handlers
2. enforce `S7` legal transitions only
3. return deterministic errors:
   - `ERR_TURN_NOT_STEERABLE`
   - `ERR_TURN_TERMINAL`
   - `ERR_ACTIVE_TURN_MISMATCH`
4. ensure terminal invariants:
   - one terminal completion
   - `completedAtMs` set on terminal

Acceptance:

1. transition matrix tests pass
2. illegal transitions produce deterministic error code

## 4.3 W3 - Runtime store expansion (authoritative backend state)

Files:

1. `backend/session_core_v2/storage/runtime_store.py`
2. add `backend/session_core_v2/storage/snapshot_store.py` (in-memory baseline acceptable in P2)

Tasks:

1. persist turn index per thread:
   - active turn pointer
   - turn status
   - turn timestamps
2. persist item index per turn:
   - item lifecycle + payload patching
3. append event envelopes with monotonic `eventSeq`
4. expose replay read API:
   - from cursor (`Last-Event-ID`)
   - bounded page/window
5. bump snapshot metadata per `S5` cadence policy (in-memory baseline allowed)

Acceptance:

1. journal event ordering strictly monotonic per thread
2. replay from same cursor deterministic

## 4.4 W4 - Idempotency ledger for mutating turn actions

Files:

1. `backend/session_core_v2/storage/runtime_store.py` (or dedicated idempotency module)
2. `backend/session_core_v2/connection/manager.py`
3. `backend/routes/session_v4.py`

Tasks:

1. require `clientActionId` for:
   - `turn/start`
   - `turn/steer`
   - `turn/interrupt`
2. persist idempotency records with payload hash and accepted result hash
3. duplicate rules:
   - same key + same payload => return previous result
   - same key + different payload => `ERR_IDEMPOTENCY_PAYLOAD_MISMATCH`

Acceptance:

1. duplicate submit behavior stable across reconnect
2. idempotency tests pass for all 3 turn mutations

## 4.5 W5 - Event router + backpressure (Codex-style)

Files:

1. add `backend/session_core_v2/events/stream_router.py`
2. add `backend/session_core_v2/events/replay.py`
3. update `backend/routes/session_v4.py` events endpoint

Tasks:

1. serve SSE stream from journal cursor
2. support `Last-Event-ID` header parsing (`<threadId>:<eventSeq>`)
3. lag behavior:
   - bounded subscriber queues
   - lagged subscriber reset, never block producer
   - reconnect + replay by cursor
4. error behavior:
   - invalid cursor => `ERR_CURSOR_INVALID`
   - expired cursor => `ERR_CURSOR_EXPIRED` + snapshot pointer

Acceptance:

1. no producer stall under slow subscriber test
2. reconnect replay recovers ordered stream

## 4.6 W6 - Route enablement and phase gating updates

Files:

1. `backend/routes/session_v4.py`
2. `backend/tests/integration/test_session_v4_api.py`

Tasks:

1. replace `ERR_PHASE_NOT_ENABLED` handlers for 3 turn endpoints + events endpoint
2. keep request resolution endpoints phase-gated in P2
3. keep thread advanced utilities (`fork/loaded/unsubscribe/...`) gated unless explicitly pulled into P2.5

Acceptance:

1. turn + events endpoints return contract-compliant envelopes
2. non-P2 endpoints continue deterministic `501` gate behavior

## 4.7 W7 - Test matrix and parity fixtures

New/updated tests:

1. `backend/tests/unit/test_session_v2_turn_state_machine.py` (new)
2. `backend/tests/unit/test_session_v2_runtime_store.py` (new)
3. `backend/tests/unit/test_session_v2_idempotency.py` (new)
4. `backend/tests/integration/test_session_v4_events.py` (new)
5. `backend/tests/integration/test_session_v4_api.py` (extend)
6. contract schema checks for turn/event envelopes

Required scenarios:

1. start turn baseline
2. steer happy path + `expectedTurnId` mismatch
3. interrupt from `inProgress` and `waitingUserInput`
4. duplicate `clientActionId` same payload
5. duplicate `clientActionId` payload mismatch
6. terminal turn mutation rejection
7. replay from cursor
8. lagged subscriber reset + reconnect recovery

## 4.8 W8 - Observability and rollout safety

Files:

1. `backend/main.py`
2. session core v2 modules (logging points)

Tasks:

1. add Phase 2 runtime flags:
   - `SESSION_CORE_V2_ENABLE_TURNS`
   - `SESSION_CORE_V2_ENABLE_EVENTS`
2. emit structured logs:
   - threadId, turnId, clientActionId, eventSeq, errorCode
3. backpressure telemetry:
   - queue depth
   - lagged reset count
   - cursor expired count
   - replay recovery success/fail

Acceptance:

1. rollback to Phase 1 behavior via config only
2. no destructive data migration required

## 5. Phase 2 execution order (recommended)

1. W1 protocol client extensions
2. W2 turn service + manager wiring
3. W3 runtime store expansion
4. W4 idempotency ledger
5. W5 events router + replay
6. W6 route enablement
7. W7 full test matrix
8. W8 flags/telemetry hardening

Rule:

1. No frontend/business coupling during P2.
2. Keep all changes inside `session_core_v2` lane and `/v4/session/*`.

## 6. Exit criteria (Phase 2 gate)

Phase 2 is PASS only when all conditions hold:

1. turn endpoints + events endpoint are enabled and contract-conformant
2. `S7` transition matrix enforced with deterministic errors
3. `S6` idempotency behaviors pass duplicate/retry tests
4. replay/cursor behavior meets `S5` contract (`ERR_CURSOR_EXPIRED` deterministic)
5. slow consumer cannot stall producer
6. all P2 tests green
7. legacy `/v3` behavior unchanged

## 7. Verification command set (target)

1. `python -m pytest -q backend/tests/unit/test_session_v2_connection_state_machine.py backend/tests/unit/test_session_v2_protocol_client.py`
2. `python -m pytest -q backend/tests/unit/test_session_v2_turn_state_machine.py backend/tests/unit/test_session_v2_runtime_store.py backend/tests/unit/test_session_v2_idempotency.py`
3. `python -m pytest -q backend/tests/integration/test_session_v4_api.py backend/tests/integration/test_session_v4_events.py`

## 8. Key risks and mitigations

1. Risk: request/approval events xuất hiện giữa turn làm flow kẹt khi P3 chưa mở.
   - Mitigation: keep request resolution endpoints gated; run P2 scenarios với policy tránh approval-required paths; log and surface pending request as deterministic blocked state.
2. Risk: event flood gây memory pressure.
   - Mitigation: bounded subscriber queues + lagged reset + cursor replay path.
3. Risk: contract drift giữa PlanningTree và Codex.
   - Mitigation: lock method/event names exactly as Codex schema; extend parity fixture checks before gate.
4. Risk: accidental dependency vào legacy modules.
   - Mitigation: enforce import guard in tests (`session_core_v2` must not import `backend/ai/codex_client.py`).

## 9. Phase 2.5 (optional, only if P2 stable early)

If schedule allows after P2 gate is near-green, pull one optional bundle:

1. `thread/fork`
2. `thread/loaded/list`
3. `thread/unsubscribe`

Rule:

1. only start P2.5 when core turn runtime and events tests are already stable.
2. do not delay P2 gate for optional bundle.
