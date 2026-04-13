# C1 Event Stream Contract v1

Status: Frozen for current implementation wave.

Owner: backend + frontend conversation pipeline.

## Scope

Defines canonical thread stream envelopes for streaming, replay, and frontend apply.

Two envelope classes are in scope:

- replayable business frames
- non-replayable control frames

## Envelope Classes

### Business frame envelope (replayable)

Canonical fields:

- `schema_version` (integer)
- `event_id` (string; monotonic per thread)
- `event_type` (string)
- `thread_id` (string)
- `turn_id` (string or null)
- `snapshot_version` (integer or null)
- `occurred_at_ms` (integer, epoch milliseconds)
- `payload` (object)

Schema:

- `c1-event-stream-envelope-v1.schema.json`

### Control frame envelope (non-replayable)

Canonical fields:

- `schema_version` (integer)
- `event_type` (`stream_open` or `replay_miss`)
- `thread_id` (string)
- `turn_id` (string or null)
- `snapshot_version` (integer or null)
- `occurred_at_ms` (integer, epoch milliseconds)
- `payload` (object)

Optional:

- `event_id` may be absent and is never required for replay cursor progression.

Schema:

- `c1-event-stream-control-envelope-v1.schema.json`

## Invariants

1. Every replayable business event includes all business canonical fields.
2. `event_id` ordering equals apply ordering for a thread stream.
3. `event_id` continuity survives process restart for the same thread.
4. Control frames are non-replayable and do not advance replay cursor.
5. Heartbeat is transport-only and never changes replay cursor.
6. Envelope schema version is explicit and validated.

## Allowed Event Types (minimum set)

Replayable business frames:

- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `thread.lifecycle.v3`
- `conversation.ui.plan_ready.v3`
- `conversation.ui.user_input.v3`
- `thread.error.v3`

Control frames:

- `stream_open` (stream metadata frame)
- `replay_miss` (explicit out-of-window replay signal)

## Prohibited Behaviors

- replayable business events without `event_id`
- heartbeat frames entering replay history
- silent continuation after replay gap mismatch
- producer-specific field naming drift without contract mapping

## Enforcement

1. Schema check against:
   - `c1-event-stream-envelope-v1.schema.json` (business frames)
   - `c1-event-stream-control-envelope-v1.schema.json` (control frames)
2. Compatibility test set for producer/consumer contract.
3. Phase gate checks for heartbeat cursor pollution and replay boundary duplicates.
