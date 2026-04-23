# S5 Durability and Replay Contract v1

Status: Normative

## Core rule

Journal persistence is authoritative.
Frontend state is never required for replay/resume correctness.

## Event identity

1. Each thread has a monotonic `eventSeq` (`uint64`).
2. Event identifier is composite:
   - `eventId = "<threadId>:<eventSeq>"`
3. Ordering for a thread is strictly by `eventSeq`.

## Cursor semantics

1. Cursor means "last fully applied `eventSeq`".
2. Replay start position is `cursor + 1`.
3. Missing cursor defaults to stream head for live mode or earliest retained event for replay mode.

## Snapshot semantics

Each snapshot stores:

1. `snapshotVersion` (monotonic per thread)
2. `thread` state
3. `turn` index
4. `item` index
5. `pendingRequest` index
6. `lastEventSeq`

Default cadence target:

1. every 200 Tier 0 events, or
2. every 10 seconds,
3. whichever comes first.

## Retention

Minimum production retention target:

1. at least 7 days, or
2. at least 200000 events per thread,
3. whichever is larger.

## Cursor miss behavior

If cursor is outside retention window:

1. return deterministic error `ERR_CURSOR_EXPIRED`
2. include latest snapshot pointer and `lastEventSeq`
3. require snapshot-based resync then replay forward from available journal tail

No silent fallback is allowed.

## Replay correctness invariants

1. Replaying from same `(threadId, cursor)` is deterministic.
2. Tier 0 replay output is byte-for-byte stable for envelope fields.
3. Applying replay then live events preserves strict `eventSeq` monotonicity.

## Lagged subscriber behavior

1. Subscriber queue overflow does not block producer.
2. Lagged subscriber is reset.
3. Recovery uses replay by cursor.
4. If cursor expired, use snapshot resync path.

