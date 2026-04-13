# Phase 02 - Replay and Gap Recovery

Status: Completed (ready for Phase 03 handoff).

Scope IDs: B02, B03, B05.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Implements Goose-style reconnect correctness before downstream performance tuning.

Contract focus:

- Primary: `C2` Replay and Resync Contract v1
- Secondary: `C1` Event Stream Contract v1

Must-hold decisions:

- Reconnect cursor uses canonical `event_id`.
- Cursor transport supports both `Last-Event-ID` header and `last_event_id` query, with header precedence.
- Replay miss must return HTTP `409` with `conversation_stream_mismatch` and `replay_miss` semantics, then trigger targeted resync.
- Replay/live boundary must be deduplicated deterministically.


## Objective

Make reconnect behavior robust by replaying only missing events and handling replay gaps explicitly.

## Prerequisite

Phase 01 completed (stable event IDs and cursor semantics).

Reference handoff:

- `docs/render/phases/phase-01-stream-contract-foundation/handoff-to-phase-02.md`

Output handoff:

- `docs/render/phases/phase-02-replay-gap-recovery/handoff-to-phase-03.md`

## In Scope

1. B02: Server replay buffer.
2. B03: Gap detection with controlled resync path.
3. B05: Retry policy tuning.

## Detailed Improvements

### 1. Replay buffer per thread/session (B02)

Implement bounded replay history:

- ring buffer keyed by thread/session
- stores only replayable business events
- configurable limits (event count and/or memory)

Expected result: reconnect can recover missing range without full snapshot reload in most cases.

### 2. Explicit gap handling (B03)

If client asks replay from event ID older than retained window:

- server returns explicit replay-miss signal
- frontend executes targeted resync flow
- do not silently continue with inconsistent state

### 3. Retry/backoff policy (B05)

Client reconnect policy:

- exponential backoff
- random jitter
- bounded max backoff
- reset backoff on healthy stream period

Goal: avoid reconnect storms and reduce thundering herd.

## Implementation Plan

1. Backend:
   - Add replay buffer storage and retention policy (`max_events=500`, `ttl=15m`, business events only).
   - Expose replay fetch by cursor (`Last-Event-ID` header or `last_event_id` query; header wins).
   - Return explicit `409 conversation_stream_mismatch` with `replay_miss` semantics for out-of-window cursor.
2. Frontend:
   - Persist latest known cursor.
   - On reconnect, request replay from cursor via `last_event_id` query (EventSource-compatible path).
   - If mismatch (`409`), trigger targeted snapshot/event resync flow.
3. Transport:
   - Keep retry/backoff parameters configurable and cursor-safe.

## Quality Gates

1. Reconnect correctness:
   - mid-stream disconnect reconnects without lost messages in standard range.
2. Replay efficiency:
   - reduced full reload fallbacks in reconnect scenarios.
3. Stability:
   - reconnect attempts are rate-limited by policy under unstable network.

## Test Plan

1. Integration tests:
   - disconnect/reconnect within replay window (no loss, no duplicate).
   - disconnect/reconnect outside replay window (explicit `409 replay_miss` contract).
2. Fault injection:
   - intermittent network drop simulation with repeated reconnects.
3. Manual checks:
   - verify no duplicate apply at replay/live boundary.

## Risks and Mitigations

1. Risk: memory growth from replay buffer.
   - Mitigation: bounded ring + eviction metrics/logs.
2. Risk: inconsistent frontend behavior on replay miss.
   - Mitigation: one explicit resync state machine and UI status indicator.

## Handoff to Phase 03

After this phase, backend/frontend can reduce event volume safely because reconnect correctness is no longer coupled to full reload behavior.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-6 engineering days
- Suggested staffing: 1 backend + 1 frontend (shared)
- Confidence level: Medium (depends on current code-path complexity and test debt)





