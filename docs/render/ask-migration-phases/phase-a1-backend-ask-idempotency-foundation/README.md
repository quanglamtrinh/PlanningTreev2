# Phase A1 - Backend Ask Idempotency Foundation

Status: Planned.

Phase ID: `AQ1`.

## Objective

Add deterministic idempotency handling for ask-lane turn starts so retries and reconnects do not create duplicate turns.

## Why This Phase First

Queueing ask sends without idempotency makes duplicate turn creation likely during network instability or client retries.

## Baseline Observation

`thread_runtime_service_v3.start_turn(...)` currently drops metadata (`del metadata`), so ask turn start does not yet use a request key for dedupe.

## In Scope

1. Accept `idempotencyKey` for ask lane turn start.
2. Persist dedupe mapping for ask lane start requests.
3. Return consistent response for repeated key:
   - same `turnId`
   - same `threadId`
   - stable accepted payload semantics
4. Define TTL/lifecycle for stored dedupe entries.

## Out of Scope

1. UI queue implementation.
2. Ask queue policy and controls.
3. Execution idempotency redesign (execution remains unchanged).

## Implementation Plan

1. Route/runtime:
   - pass ask metadata key through by-id start flow.
2. Runtime service:
   - consume metadata key in `start_turn`.
   - add dedupe lookup before creating a new turn.
3. Storage:
   - store request key to turn mapping with bounded retention.
4. Error policy:
   - define behavior for malformed/empty keys.

## Quality Gates

1. Dedupe correctness:
   - repeated same key does not create new turn.
2. Stability:
   - no regression for non-idempotent sends when key absent.
3. Compatibility:
   - execution lane behavior unchanged.

## Test Plan

1. Unit tests:
   - same key replay returns same turn payload.
   - different key creates new turn.
2. Integration tests:
   - retry start-turn request under transient failure conditions.
3. Regression tests:
   - execution start-followup remains unchanged.

## Risks and Mitigations

1. Risk: key retention too short creates duplicate after reconnect.
   - Mitigation: tune TTL to cover expected reconnect window.
2. Risk: key retention too long causes stale collisions.
   - Mitigation: include thread/lane scoping and bounded expiry.

## Exit Criteria

1. Ask start-turn dedupe is deterministic and test-covered.
2. A2-A3 can rely on backend duplicate protection.

## Effort Estimate

- Size: Medium
- Estimated duration: 2-4 engineering days
- Suggested staffing: 1 backend primary

