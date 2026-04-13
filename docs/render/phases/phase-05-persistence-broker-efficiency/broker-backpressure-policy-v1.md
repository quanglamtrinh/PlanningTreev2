# Phase 05 Broker Backpressure Policy v1

Status: Frozen artifact for `broker_backpressure_policy_frozen`.

Owner: backend SSE transport.

Date: 2026-04-13.

## Purpose

Define explicit, contract-safe slow-consumer behavior for Phase 05 transport optimization.

## Policy

1. Queue model:
   - subscriber queue is bounded.
   - default `maxsize` is `128`.
   - runtime config: `PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX`.
2. Overflow behavior:
   - on `QueueFull`, subscriber is marked lagged.
   - stream is closed intentionally on lag detection.
   - client recovery path is reconnect + replay via C2 cursor semantics.
3. Recovery:
   - no silent drop continuation for lagged subscriber.
   - no `drop_oldest` buffering policy.
   - no fallback full-reload without explicit replay-miss classification.

## Contract Mapping

- C1: no new public event types required for lag closure.
- C2: replay cursor remains source-of-truth; reconnect remains deterministic.
- C4: transport backpressure policy must not bypass durability boundaries.

## Required Runtime Guarantees

1. Lag closure must not produce cursor regression.
2. Replay/live handoff dedupe must remain deterministic.
3. Slow-consumer incidents are considered handled only if closure + replay path is available.

## Prohibited Behaviors

- unbounded subscriber queues in Phase 05 path.
- hidden data loss via silent queue overflow.
- contract-breaking control-frame additions without C1 freeze update.
