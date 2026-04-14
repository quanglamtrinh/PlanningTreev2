# Render Optimization Phase Plan (A-E Only)

Status: A-E execution plan completed (Phase 01-13 completed).

Last updated: 2026-04-14.

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

## Decision Authority

All phase implementation decisions in this folder are governed by:

- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/README.md`

If a phase note conflicts with the Decision Pack, the Decision Pack wins until explicitly revised.

## Required Preflight

Before starting any phase implementation:

1. Run `npm run check:render_freeze`.
2. Confirm the corresponding phase entry criteria in `docs/render/system-freeze/phase-manifest-v1.json`.
3. Confirm phase gate IDs and targets in `docs/render/system-freeze/phase-gates-v1.json`.
4. Record phase-specific implementation values in the phase technical design note.

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

1. [phase-01-stream-contract-foundation](./phase-01-stream-contract-foundation/README.md) (B01, B04, B06)
2. [phase-02-replay-gap-recovery](./phase-02-replay-gap-recovery/README.md) (B02, B03, B05)
3. [phase-03-backend-delta-compaction](./phase-03-backend-delta-compaction/README.md) (A01, A04, A08)
4. [phase-04-inmemory-actor-checkpointing](./phase-04-inmemory-actor-checkpointing/README.md) (A02, A03)
5. [phase-05-persistence-broker-efficiency](./phase-05-persistence-broker-efficiency/README.md) (A05, A06, A07) - Completed
6. [phase-06-frame-batching-fast-append](./phase-06-frame-batching-fast-append/README.md) (C01, C07) - Completed
7. [phase-07-state-shape-hot-path](./phase-07-state-shape-hot-path/README.md) (C02, C03, C04) - Completed
8. [phase-08-store-isolation-selectors](./phase-08-store-isolation-selectors/README.md) (C05, C06, C08) - Completed
9. [phase-09-row-isolation-cache](./phase-09-row-isolation-cache/README.md) (D01, D02, D10) - Completed
10. [phase-10-progressive-virtualized-rendering](./phase-10-progressive-virtualized-rendering/README.md) (D03, D04, D09) - Completed
11. [phase-11-heavy-compute-off-main-thread](./phase-11-heavy-compute-off-main-thread/README.md) (D05, D06, D07) - Completed
12. [phase-12-data-volume-and-heavy-content-ux](./phase-12-data-volume-and-heavy-content-ux/README.md) (D08, E01, E02, E03) - Completed
13. [phase-13-queued-follow-up-flow](./phase-13-queued-follow-up-flow/README.md) (E04, E05, E06) - Completed

## Contract Coverage Matrix

| Phase | Primary contracts |
|---|---|
| 01 | C1, C2 |
| 02 | C2, C1 |
| 03 | C1, C3, C4 |
| 04 | C4, C3 |
| 05 | C4, C2, C1 |
| 06 | C5, C1 |
| 07 | C5 |
| 08 | C5, C2, C3 |
| 09 | C5 |
| 10 | C5 |
| 11 | C5 |
| 12 | C5, C4 |
| 13 | C6, C3 |

## Effort Overview

| Phase | Scope IDs | Size | Estimated duration |
|---|---|---|---|
| 01 | B01, B04, B06 | Medium | 3-4 engineering days |
| 02 | B02, B03, B05 | Medium | 4-6 engineering days |
| 03 | A01, A04, A08 | Medium | 4-6 engineering days |
| 04 | A02, A03 | Large | 6-8 engineering days |
| 05 | A05, A06, A07 | Large | 6-9 engineering days |
| 06 | C01, C07 | Medium | 4-5 engineering days |
| 07 | C02, C03, C04 | Large | 5-7 engineering days |
| 08 | C05, C06, C08 | Medium | 4-6 engineering days |
| 09 | D01, D02, D10 | Medium | 4-5 engineering days |
| 10 | D03, D04, D09 | Large | 6-8 engineering days |
| 11 | D05, D06, D07 | Large | 6-8 engineering days |
| 12 | D08, E01, E02, E03 | Medium | 4-6 engineering days |
| 13 | E04, E05, E06 | Medium | 4-6 engineering days |

Estimate notes:

- Duration is for implementation + validation in one phase, excluding large refactor surprises.
- Parallel staffing can reduce calendar time but increases coordination overhead.

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
