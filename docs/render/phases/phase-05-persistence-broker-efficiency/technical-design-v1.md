# Phase 05 Technical Design v1

Status: Frozen implementation design.

Date: 2026-04-13.

Phase: `phase-05-persistence-broker-efficiency` (A05, A06, A07).

## 1. Runtime Parameters

1. `PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX`:
   - default: `128`.
   - bounds: `1..4096`.
2. `PLANNINGTREE_P05_LOG_COMPACT_MIN_EVENTS`:
   - default: `200`.
   - bounds: `>= 1`.
3. Actor mode for benchmark/evidence:
   - `PLANNINGTREE_THREAD_ACTOR_MODE=on`.

## 2. Persistence Design (A05)

1. Added store: `ThreadEventLogStoreV3`.
2. Record model: `ThreadEventLogRecordV3`.
3. Append path:
   - actor-on mutation publish appends replayable envelopes to event-log.
4. Recovery path:
   - bootstrap loads latest snapshot.
   - validates event-log sequence/order.
   - replays tail envelopes where `snapshotVersionAtAppend > snapshot.snapshotVersion`.
5. Compaction:
   - after successful checkpoint, prune log entries before checkpoint event-id cursor.
   - compaction runs only when entry count meets threshold.

## 3. Broker Design (A06 + A07)

1. Fanout:
   - publish deep-copies payload once per publish operation.
   - fans out shared cloned payload to subscribers.
2. Backpressure:
   - queues are bounded.
   - `QueueFull` sets lagged signal.
   - SSE route closes lagged stream intentionally.

## 4. Failure Handling

1. Event-log replay validation is fail-closed on:
   - `logSeq` gap.
   - non-monotonic `eventId`.
   - unsupported/invalid replay envelope shape.
2. Compaction failure does not fail checkpoint commit; it logs warning and keeps data.

## 5. Gate Harness Mapping

1. `P05-G1` source: `scripts/phase05_persist_load_benchmark.py`.
2. `P05-G2` source: `scripts/phase05_broker_profile_run.py`.
3. `P05-G3` source: `scripts/phase05_slow_subscriber_stress.py`.
4. Consolidation: `scripts/phase05_gate_report.py`.
