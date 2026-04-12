# Phase 04 - In-Memory Actor and Checkpointing

Status: Planned.

Scope IDs: A02, A03.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Establishes correctness-first runtime ownership and durability boundaries before full persistence expansion.

Contract focus:

- Primary: `C4` Durability Contract v1
- Secondary: `C3` Lifecycle and Gating Contract v1

Must-hold decisions:

- This phase includes mini-journal durability (not snapshot-only).
- Checkpoint triggers must follow lifecycle contract boundaries.
- Crash-loss budget must be explicitly defined and validated.


## Objective

Replace repeated snapshot reads/writes in the hot path with an in-memory thread actor and policy-driven checkpoints.

## In Scope

1. A02: In-memory thread actor model.
2. A03: Checkpoint by boundary/timer, not per event.
3. Decision Pack constraint: include mini-journal durability in this phase.

## Detailed Improvements

### 1. Thread actor ownership model (A02)

Each active thread gets one runtime actor that owns:

- current thread state
- ordered event inbox
- mutable projection context

Processing model:

- load snapshot once on actor bind
- apply compacted events in memory
- emit outbound stream events

### 2. Boundary-based checkpointing (A03)

Persist snapshot on:

- turn terminal events (`turn_completed`, `turn_failed`)
- waiting/gated boundaries (`waiting_user_input`)
- periodic timer (safety checkpoint)
- actor eviction/shutdown

This removes per-delta snapshot writes from critical path.

## Implementation Plan

1. Runtime:
   - Introduce actor registry with lifecycle (create, active, evict).
   - Route thread events through actor inbox.
2. Persistence:
   - Move snapshot write trigger to checkpoint policy.
   - Keep explicit flush API for forced consistency points.
3. Recovery:
   - On restart, rebuild actor state from latest snapshot + pending events (if available).

## Quality Gates

1. Throughput:
   - `snapshot_reads_per_turn` and `snapshot_writes_per_turn` reduced materially.
2. Correctness:
   - no event loss across actor create/evict boundaries.
3. Stability:
   - lock contention and hot-path wait times improve.

## Test Plan

1. Unit tests:
   - actor serialization order and mailbox behavior.
   - checkpoint trigger matrix.
2. Integration tests:
   - long streaming turn with forced actor eviction/reload.
3. Crash/restart simulation:
   - recover to consistent thread state after unclean stop.

## Risks and Mitigations

1. Risk: stale actor state after missed checkpoint.
   - Mitigation: bounded checkpoint interval + forced flush on terminal events.
2. Risk: memory pressure from too many active actors.
   - Mitigation: LRU eviction with safe checkpoint before removal.

## Handoff to Phase 05

With actor + checkpointing in place, persistence and broker optimizations can be introduced without fighting per-event disk I/O.


## Effort Estimate

- Size: Large
- Estimated duration: 6-8 engineering days
- Suggested staffing: 1 backend primary + 1 backend reviewer
- Confidence level: Medium (depends on current code-path complexity and test debt)





