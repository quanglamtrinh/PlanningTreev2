# C4 Durability Contract v1

Status: Frozen durability and recovery contract.

Owner: backend runtime actor + persistence layer.

## Scope

Defines checkpoint triggers, mini-journal requirements, crash recovery guarantees, and persistence migration safety.

## Required Behaviors

1. Checkpoint triggers include:
   - terminal boundaries (`turn_completed`, `turn_failed`)
   - gated boundaries (`waiting_user_input`)
   - periodic safety timer
   - actor eviction/shutdown
2. Phase 04 includes mini-journal durability (snapshot-only is not allowed).
3. Recovery path is deterministic from persisted artifacts.
4. Crash-loss budget is explicitly defined and tested.

## Mini-Journal Baseline (Phase 04)

- record recovery-critical boundaries and event ranges
- replay from mini-journal to restore state between snapshots

## Full Hybrid Target (Phase 05)

- append-only event log + periodic compact snapshot
- deterministic reconstruction path from snapshot + tail events

## Prohibited Behaviors

- unbounded checkpoint delay without explicit crash-loss acceptance
- durability semantics changing silently across phases
- recovery behavior depending on volatile-only in-memory state

