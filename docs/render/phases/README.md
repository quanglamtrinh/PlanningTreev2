# Render Optimization Phase Plan (A-E Only)

Status: Draft approved for implementation planning.

Last updated: 2026-04-11.

## Scope Boundary

This phase plan intentionally includes only Layer A-E from the comprehensive backlog:

- Layer A: backend ingest, projection, persistence
- Layer B: SSE reliability and reconnect
- Layer C: frontend state pipeline
- Layer D: render and component performance
- Layer E: data volume and UX flow

Temporarily excluded:

- Layer F: observability, profiling, test infrastructure expansion
- Layer G: rollout and safety program

## Why This Split

The goal is to create execution momentum on core latency and responsiveness first, while keeping each phase small enough to protect quality.

## Global Quality Bar (applies to every phase)

A phase is considered complete only when all checks below are true:

1. Functional correctness:
   - No contract break between backend events and frontend render behavior.
   - No message loss in standard interaction flow.
2. Performance validation:
   - The phase-specific target metrics improve versus baseline.
   - No major regression in adjacent metrics.
3. Stability:
   - Disconnect/reconnect and long-thread behavior remain usable.
   - No sustained CPU spikes or UI freeze in manual smoke tests.
4. Test coverage:
   - Unit/integration tests for new logic paths are added or updated.
   - Existing relevant tests continue to pass.
5. Documentation:
   - Decision, trade-offs, and known limitations are recorded in the phase doc.

## Phase Sequence

1. [phase-01-stream-contract-foundation.md](./phase-01-stream-contract-foundation.md) (B01, B04, B06)
2. [phase-02-replay-gap-recovery.md](./phase-02-replay-gap-recovery.md) (B02, B03, B05)
3. [phase-03-backend-delta-compaction.md](./phase-03-backend-delta-compaction.md) (A01, A04, A08)
4. [phase-04-inmemory-actor-checkpointing.md](./phase-04-inmemory-actor-checkpointing.md) (A02, A03)
5. [phase-05-persistence-broker-efficiency.md](./phase-05-persistence-broker-efficiency.md) (A05, A06, A07)
6. [phase-06-frame-batching-fast-append.md](./phase-06-frame-batching-fast-append.md) (C01, C07)
7. [phase-07-state-shape-hot-path.md](./phase-07-state-shape-hot-path.md) (C02, C03, C04)
8. [phase-08-store-isolation-selectors.md](./phase-08-store-isolation-selectors.md) (C05, C06, C08)
9. [phase-09-row-isolation-cache.md](./phase-09-row-isolation-cache.md) (D01, D02, D10)
10. [phase-10-progressive-virtualized-rendering.md](./phase-10-progressive-virtualized-rendering.md) (D03, D04, D09)
11. [phase-11-heavy-compute-off-main-thread.md](./phase-11-heavy-compute-off-main-thread.md) (D05, D06, D07)
12. [phase-12-data-volume-and-heavy-content-ux.md](./phase-12-data-volume-and-heavy-content-ux.md) (D08, E01, E02, E03)
13. [phase-13-queued-follow-up-flow.md](./phase-13-queued-follow-up-flow.md) (E04, E05, E06)

## Dependency Flow

- Phase 1-2 establish stream correctness/reconnect behavior.
- Phase 3-5 reduce backend event and persistence pressure.
- Phase 6-8 reduce frontend apply churn and invalidation fanout.
- Phase 9-11 improve render pipeline under normal and heavy payloads.
- Phase 12-13 optimize UX behavior under long-running/active turns.

## Suggested Execution Rhythm

1. Start each phase with a short technical design note.
2. Implement in small PR-sized slices, not one large merge.
3. Run phase exit checklist before moving to next phase.
4. Record unresolved debt in the next phase doc under "Carry-over".
