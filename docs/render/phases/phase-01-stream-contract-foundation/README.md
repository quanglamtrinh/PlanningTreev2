# Phase 01 - Stream Contract Foundation

Status: Planned.

Scope IDs: B01, B04, B06.

Subphase workspace: ./subphases/.


## Objective

Create a strict, stable SSE event contract so reconnect logic and frontend apply behavior are deterministic.

## Why This Phase First

If stream semantics are unstable, every later optimization can create hidden correctness bugs. We first lock event identity, cursor behavior, and first-frame semantics.

## In Scope

1. B01: SSE event IDs + replay cursor base contract.
2. B04: Heartbeat policy that does not pollute replay cursor.
3. B06: First meaningful frame optimization.

## Detailed Improvements

### 1. Event envelope standardization (B01)

Define one business event envelope used by all stream producers:

- `id`: monotonic per-thread stream ID
- `event_type`: semantic type (item_patch, lifecycle_update, etc.)
- `thread_id`
- `turn_id` (nullable for non-turn events)
- `created_at_ms`
- `payload`

Rules:

- Every business event must include `id`.
- `id` ordering must match apply ordering.
- Frontend stores `last_event_id` only from business events.

### 2. Heartbeat isolation (B04)

Heartbeat is transport health only:

- Uses `event: heartbeat`
- Does not advance replay cursor
- Does not enter replay history
- Does not trigger store mutation in frontend

### 3. First meaningful frame (B06)

Emit a lightweight `stream_open` event immediately after subscribe:

- current thread lifecycle state
- active request IDs (if any)
- server replay window metadata (size/time)

Goal: allow frontend to render stream-aware status quickly without waiting for heavy payloads.

## Implementation Plan

1. Backend:
   - Add shared event envelope builder in stream layer.
   - Update workflow stream route to always emit standardized fields.
   - Separate heartbeat path from business event path.
2. Frontend:
   - Update SSE client parser for strict envelope schema.
   - Persist `last_event_id` only for replayable business events.
   - Use `stream_open` for initial stream status hydration.
3. Compatibility:
   - Keep temporary backward-compatible parsing for old fields during migration window.

## Quality Gates

1. Contract correctness:
   - 100% business events include valid `id`.
   - Event IDs strictly monotonic per thread.
2. Cursor correctness:
   - Heartbeat never changes `last_event_id`.
3. UX:
   - `time_to_first_meaningful_frame` improves versus baseline in manual test.

## Test Plan

1. Unit tests:
   - Event envelope schema and ID assignment.
   - Heartbeat filtering logic.
2. Integration tests:
   - Stream open sequence emits `stream_open` before normal event flow.
   - Frontend cursor update behavior excludes heartbeat.
3. Manual checks:
   - Start stream, observe quick status render.
   - Validate no duplicate/invalid IDs in logs.

## Risks and Mitigations

1. Risk: old consumers rely on legacy fields.
   - Mitigation: temporary dual parsing with deprecation note.
2. Risk: mixed ID generation paths produce collisions.
   - Mitigation: centralize ID issuance in one component.

## Handoff to Phase 02

Phase 02 can assume:

- stable `last_event_id` behavior
- deterministic event ordering
- clean separation between heartbeat and replayable events


## Effort Estimate

- Size: Medium
- Estimated duration: 3-4 engineering days
- Suggested staffing: 1 backend + 1 frontend (light FE load)
- Confidence level: Medium (depends on current code-path complexity and test debt)



