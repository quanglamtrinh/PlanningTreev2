# C2 Replay and Resync Contract v1

Status: Frozen for stream reliability phases.

Owner: backend SSE transport + frontend stream consumer.

## Scope

Defines reconnect semantics, replay cursor behavior, replay-gap handling, and replay/live handoff deduplication.

## Required Behaviors

1. Reconnect requests must provide `Last-Event-ID` semantics.
2. Server replays events where `event_id > last_event_id` while inside retention window.
3. Replay miss must return explicit mismatch signal (`replay_miss`) instead of silent continuation.
4. Client must perform targeted resync on replay miss.
5. Replay/live handoff must dedupe overlap deterministically.

## Cursor Rules

- Heartbeat never advances replay cursor.
- Non-replayable control frames never advance replay cursor.
- Business event cursor progression is monotonic.

## Backpressure and Slow Consumer

- Slow consumer handling must be explicit.
- If stream closes due to lag, reconnect+replay path must recover without duplicate apply.

## Prohibited Behaviors

- fallback to full reload without explicit mismatch classification
- duplicate apply at replay/live boundary
- replay cursor regression

