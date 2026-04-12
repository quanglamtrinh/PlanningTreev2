# C1 Event Stream Contract v1

Status: Frozen for current implementation wave.

Owner: backend + frontend conversation pipeline.

## Scope

Defines canonical thread business event envelope for streaming, replay, and frontend apply.

## Canonical Fields

- `schema_version` (integer)
- `event_id` (string; monotonic per thread)
- `event_type` (string)
- `thread_id` (string)
- `turn_id` (string or null)
- `snapshot_version` (integer or null)
- `occurred_at_ms` (integer, epoch milliseconds)
- `payload` (object)

## Invariants

1. Every replayable business event includes all canonical fields.
2. `event_id` ordering equals apply ordering for a thread stream.
3. `event_id` continuity survives process restart for the same thread.
4. Heartbeat is transport-only and never changes replay cursor.
5. Envelope schema version is explicit and validated.

## Allowed Event Types (minimum set)

- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `thread.lifecycle.v3`
- `conversation.ui.plan_ready.v3`
- `conversation.ui.user_input.v3`
- `thread.error.v3`
- `stream_open` (stream metadata frame)
- `replay_miss` (explicit out-of-window replay signal)

## Prohibited Behaviors

- replayable business events without `event_id`
- heartbeat frames entering replay history
- silent continuation after replay gap mismatch
- producer-specific field naming drift without contract mapping

## Enforcement

1. Schema check against `c1-event-stream-envelope-v1.schema.json`.
2. Compatibility test set for producer/consumer contract.
3. Phase gate checks for heartbeat cursor pollution and replay boundary duplicates.

