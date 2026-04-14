# Subphase 01 - Stream Contract Foundation Implementation Note

Status: Implemented.

Date: 2026-04-12.

Owner: PTM core conversation pipeline.

## Scope Implemented

- B01: canonical C1 envelope + SSE `id` alignment for replayable business events.
- B04: heartbeat isolation from cursor semantics.
- B06: first meaningful frame via `stream_open` control frame.

## Code-Level Changes

### Backend

- Canonical + legacy dual-write envelope production:
  - `backend/conversation/domain/events.py`
- Durable monotonic `event_id` issuance per thread via registry metadata:
  - `backend/conversation/domain/types.py`
  - `backend/conversation/services/thread_registry_service.py`
  - `backend/conversation/services/thread_query_service_v3.py`
- SSE frame separation:
  - replayable business frame -> has SSE `id` from canonical `event_id`
  - `stream_open` control frame -> no SSE `id`
  - heartbeat -> comment frame `: heartbeat`
  - `backend/routes/workflow_v3.py`

### Frontend

- Canonical-first parser with controlled legacy fallback and hard error on contract mismatch:
  - `frontend/src/features/conversation/state/threadEventRouter.ts`
- Cursor semantics:
  - update `lastEventId` only on validated replayable business events
  - `stream_open` does not advance cursor
  - non-monotonic or duplicate `event_id` triggers controlled error + snapshot reload fallback
  - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- Optional local debugging counters (non-gating in this wave):
  - `legacy_fallback_used_count`
  - `envelope_validation_failure_count`
  - `heartbeat_cursor_pollution_count`

## Gate Measurement Plan (P01-G1..P01-G3)

### P01-G1

Gate: `contract_envelope_validation_pass_rate_pct >= 100`

Measurement method:

1. Backend producer emits canonical fields for replayable business events and dual-writes legacy aliases.
2. Frontend parser validates envelope contract and raises hard error on malformed/mixed-inconsistent payloads.
3. Validation baseline from automated tests:
   - `backend/tests/unit/test_thread_query_service_v3.py`
   - `backend/tests/integration/test_chat_v3_api_execution_audit.py`
   - `frontend/tests/unit/threadByIdStoreV3.test.ts`

### P01-G2

Gate: `heartbeat_cursor_pollution_events <= 0`

Measurement method:

1. Heartbeat remains SSE comment frame (`: heartbeat`) with no payload envelope and no `id`.
2. `stream_open` is non-replayable and no-cursor.
3. Verified by automated assertions:
   - stream integration tests assert heartbeat frames are comments and not replayable business envelopes
   - store unit tests assert `stream_open` does not advance `lastEventId`
   - store unit tests assert only validated business frames advance `lastEventId`

### P01-G3

Gate: `time_to_first_meaningful_frame_p95_ms <= 1200`

Measurement method:

1. Start timestamp captured when EventSource subscription opens.
2. First meaningful frame is `stream_open`.
3. Stream smoke harness captures first meaningful frame timing from subscription start to first `stream_open`.
4. p95 gate is evaluated from smoke-test output artifacts (test-driven evidence, not runtime telemetry).

## Preflight Evidence

- Render freeze check executed:
  - `npm run check:render_freeze`
  - result: pass

## Regression and Negative Coverage Added

- Stream sequencing includes `stream_open` before snapshot.
- SSE `id` is asserted for business frames and omitted for `stream_open`.
- Legacy fallback parse path remains supported in migration window.
- Hard contract error path covers canonical/legacy mismatch handling.
- Monotonic event id issuance continuity covered across service restart.
