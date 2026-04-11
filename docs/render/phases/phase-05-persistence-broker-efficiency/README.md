# Phase 05 - Persistence and Broker Efficiency

Status: Planned.

Scope IDs: A05, A06, A07.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Extends Phase 04 durability baseline into full hybrid persistence and controlled transport behavior.

Contract focus:

- Primary: `C4 Durability Contract v1`
- Secondary: `C2 Replay and Resync Contract v1`, `C1 Event Stream Contract v1`

Must-hold decisions:

- Promote mini-journal baseline to full hybrid persistence safely.
- Backpressure handling must preserve replay/reconnect guarantees.
- Event ordering and cursor semantics must remain contract-safe.


## Objective

Lower persistence and publish overhead by reducing write amplification and controlling subscriber backpressure.

## Prerequisite

Phase 04 actor/checkpoint model is active.

## In Scope

1. A05: Hybrid persistence (event log + periodic snapshot).
2. A06: Reduce expensive deep-copy in broker.
3. A07: Bounded queue + explicit backpressure policy.

## Detailed Improvements

### 1. Hybrid persistence layout (A05)

Storage model:

- append-only event log for frequent incremental changes
- periodic compact snapshot for fast load

Benefits:

- lower rewrite cost
- better recovery flexibility

### 2. Broker payload sharing (A06)

Current risk is repeated deep-copy per subscriber. Improve by:

- immutable payload object policy, or
- one-time serialization with shared byte payload fan-out

### 3. Backpressure contract (A07)

Define queue behavior under slow consumer:

- max queue depth
- policy per mode (`drop oldest`, `close and rely on replay`, `slow-consumer warning`)
- explicit diagnostics for lagged subscribers

## Implementation Plan

1. Persistence:
   - Introduce append log writer and snapshot compactor.
   - Update read path to reconstruct from latest snapshot + tail events.
2. Broker:
   - Refactor publish path to avoid per-subscriber deep-copy.
   - Add queue depth tracking and threshold handling.
3. Error handling:
   - clear close codes/reasons for slow consumers.

## Quality Gates

1. I/O efficiency:
   - reduced write amplification and persist latency under stream load.
2. Broker efficiency:
   - lower publish CPU/allocation profile.
3. Backpressure behavior:
   - predictable handling when subscriber cannot keep up.

## Test Plan

1. Unit tests:
   - log append + snapshot compaction reconstruction correctness.
   - backpressure policy trigger behavior.
2. Integration tests:
   - multi-subscriber streaming with one intentionally slow consumer.
3. Load test:
   - sustained event burst with queue depth observation.

## Risks and Mitigations

1. Risk: reconstruction bugs from hybrid read path.
   - Mitigation: snapshot/log parity tests and deterministic replay tests.
2. Risk: shared payload mutability issues.
   - Mitigation: immutable payload contract and copy-on-write guard.

## Handoff to Phase 06

Backend now emits fewer, cheaper events, which improves the impact of frontend frame-batching work.


## Effort Estimate

- Size: Large
- Estimated duration: 6-9 engineering days
- Suggested staffing: 1 backend primary + 1 backend/infra support
- Confidence level: Medium (depends on current code-path complexity and test debt)




