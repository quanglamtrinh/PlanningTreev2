# Phase 05 - Persistence and Broker Efficiency

Status: Completed (all P05 gates passed with committed evidence).

Scope IDs: A05, A06, A07.

Subphase workspace: ./subphases/.

## Entry Criteria Artifacts

`phase-manifest-v1.json` entry criteria for Phase 05:

- `phase_04_passed`.
- `broker_backpressure_policy_frozen`.

Phase 05 entry artifacts:

- `docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/phase04-gate-report.json`.
- `docs/render/phases/phase-05-persistence-broker-efficiency/broker-backpressure-policy-v1.md`.
- `docs/render/phases/phase-05-persistence-broker-efficiency/preflight-v1.md`.
- `docs/render/phases/phase-05-persistence-broker-efficiency/technical-design-v1.md`.

Phase closure artifacts:

- `docs/render/phases/phase-05-persistence-broker-efficiency/close-phase-v1.md`.
- `docs/render/phases/phase-05-persistence-broker-efficiency/handoff-to-phase-06.md`.
- `docs/render/phases/phase-05-persistence-broker-efficiency/evidence/phase05-gate-report.json`.

Phase closure snapshot:

- `P05-G1`: `96.0` (`>= 30`).
- `P05-G2`: `95.0` (`>= 25`).
- `P05-G3`: `0` (`<= 0`).

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Extends Phase 04 durability baseline into hybrid persistence and controlled transport behavior.

Contract focus:

- Primary: `C4` Durability Contract v1.
- Secondary: `C2` Replay and Resync Contract v1, `C1` Event Stream Contract v1.

Must-hold decisions:

- Promote mini-journal baseline to full hybrid persistence safely.
- Backpressure handling must preserve replay/reconnect guarantees.
- Event ordering and cursor semantics must remain contract-safe.
- C1/C2 public envelope/event-type shape remains unchanged in this phase.

## Objective

Lower persistence and publish overhead by reducing write amplification and controlling subscriber backpressure.

## In Scope

1. A05: Hybrid persistence (append event-log + periodic snapshot checkpoint + compaction).
2. A06: Replace deep-copy-per-subscriber publish with single-copy fanout.
3. A07: Bounded queue + explicit `disconnect_and_replay` policy for slow subscribers.

## Implemented Changes

### 1. Hybrid persistence layout (A05)

- Added append-only thread event-log store (`*.event_log.jsonl`) with typed records.
- Actor-on path now appends replayable envelopes into event-log on mutation publish.
- Actor bootstrap now validates event-log continuity and replays tail envelopes after the persisted snapshot.
- Post-checkpoint compaction prunes event-log entries before checkpoint cursor when log size threshold is reached.

### 2. Broker payload sharing (A06)

- Broker publish now clones payload once per publish operation, then fans out shared object references to subscribers.
- Removed deep-copy-per-subscriber behavior from hot publish loop.

### 3. Backpressure contract (A07)

- Subscriber queues are now bounded (`maxsize` runtime-configurable; default `128`).
- Queue-full condition sets lagged signal for that subscriber.
- SSE routes close lagged stream intentionally; reconnect + replay remains canonical recovery path.

## Public Interfaces Added

1. Runtime config:
   - `PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX` (default `128`).
   - `PLANNINGTREE_P05_LOG_COMPACT_MIN_EVENTS` (default `200`).
2. Internal durability type:
   - `ThreadEventLogRecordV3`.
3. Storage adapter:
   - `ThreadEventLogStoreV3` (`append_event_record`, read-tail helpers, prune helper).

## Quality Gates

1. `P05-G1` write amplification reduction:
   - result `96.0` (`>= 30`).
2. `P05-G2` broker publish allocation reduction:
   - result `95.0` (`>= 25`).
3. `P05-G3` unhandled slow-consumer incidents:
   - result `0` (`<= 0`).

## Test Plan (Executed)

1. Unit:
   - `backend/tests/unit/test_sse_broker.py`.
   - `backend/tests/unit/test_thread_event_log_store_v3.py`.
   - `backend/tests/unit/test_thread_query_service_v3.py`.
2. Integration:
   - `backend/tests/integration/test_chat_v3_api_execution_audit.py`.
3. Governance:
   - `npm run check:render_freeze`.

## Risks and Mitigations

1. Risk: replay divergence from event-log replay on bootstrap.
   - Mitigation: fail-closed validation on log sequence/order and envelope invariants.
2. Risk: queue backpressure closes streams too aggressively under burst.
   - Mitigation: bounded queue threshold is runtime configurable and reconnect path is contract-safe.

## Handoff to Phase 06

Backend now emits cheaper fanout and reduced persistence overhead; frontend frame-batching can proceed on unchanged C1/C2 contracts.
