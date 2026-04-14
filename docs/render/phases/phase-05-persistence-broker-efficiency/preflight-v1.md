# Phase 05 Preflight v1

Status: Frozen implementation preflight.

Date: 2026-04-13.

Phase: `phase-05-persistence-broker-efficiency` (A05, A06, A07).

## 1. Entry Criteria Lock

`phase_04_passed` evidence:

- `docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/phase04-gate-report.json`.

`broker_backpressure_policy_frozen` artifact:

- `docs/render/phases/phase-05-persistence-broker-efficiency/broker-backpressure-policy-v1.md`.

## 2. Frozen Decisions for Implementation

1. Backpressure policy:
   - queue bounded by `PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX` (default `128`).
   - overflow policy is `disconnect_and_replay`.
   - `drop_oldest` and silent drop are prohibited.
2. Broker fanout:
   - single payload clone per publish operation, shared fanout to subscribers.
3. Durability:
   - append-only event-log extends Phase 04 mini-journal baseline.
   - bootstrap recovery replays event-log tail on top of latest persisted snapshot.
4. Compaction:
   - snapshot checkpoint remains lifecycle/timer-driven (C4).
   - event-log prune runs only after successful checkpoint and threshold check.

## 3. Rollout Mode Contract

Feature flag: `thread_actor_mode`.

- `off`: legacy non-actor flow.
- `shadow`: actor validation path.
- `on`: actor-authoritative durability path.

Benchmark default for Phase 05: `on`.

## 4. Compatibility and Non-Goals

Compatibility lock:

- no C1 business/control event-type additions in this phase.
- no C2 replay cursor semantics changes.
- no C3 lifecycle transition surface changes.

Non-goals:

- no Layer F observability expansion.
- no Layer G rollout/safety expansion beyond existing `off -> shadow -> on` sequence.

## 5. Gate and Evidence Lock

Phase 05 gate harness:

- `scripts/phase05_persist_load_benchmark.py`.
- `scripts/phase05_broker_profile_run.py`.
- `scripts/phase05_slow_subscriber_stress.py`.
- `scripts/phase05_gate_report.py`.

Canonical output:

- `docs/render/phases/phase-05-persistence-broker-efficiency/evidence/phase05-gate-report.json`.

## 6. Preflight Exit

No open preflight blocker remains for Phase 05 implementation under frozen contracts and defaults in this document.
