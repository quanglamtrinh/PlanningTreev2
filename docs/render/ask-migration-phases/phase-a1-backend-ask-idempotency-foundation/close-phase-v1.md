# Phase A1 Closeout v1

Status: Completed.

Date: 2026-04-15.

Phase: `phase-a1-backend-ask-idempotency-foundation` (`AQ1`).

## Closure Summary

1. Ask-lane start-turn idempotency was implemented with deterministic replay semantics keyed by `metadata.idempotencyKey`.
2. Idempotency cache is persisted in workflow `mutationCache` with contract-aligned policy:
   - key prefix `ask_start_turn_v1:`
   - TTL `20 minutes`
   - per-node cap `256`
   - prune order `TTL first`, then `LRU`
3. Conflict path for key reuse with different normalized ask text is enforced with typed `409` app error (`ask_idempotency_payload_conflict`).
4. A1 maintained frozen boundaries:
   - no queue state machine/policy/UI expansion in this phase
   - execution flow behavior unchanged
5. Ask direct-send path now injects an idempotency key when absent (`ask_turn:*`) without changing execution queue behavior.

## A1 Gate Evidence

1. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_idempotency_integration.json`
2. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_retry_replay_suite.json`
3. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_start_turn_latency_probe.json`
4. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/phase-a1-gate-report.json`

## Gate Outcome

1. `AQ1-G1` ask duplicate turn events: `0.0` (target `<= 0`, pass)
2. `AQ1-G2` ask idempotent replay success rate: `100.0` (target `>= 99`, pass)
3. `AQ1-G3` ask start-turn latency regression: `0.0` (target `<= 10`, pass)

## Validation Snapshot

1. `python -m pytest backend/tests/unit/test_thread_runtime_service_v3.py -q` -> pass (`16 passed`)
2. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "idempotent_replay_avoids_duplicate_turn_creation or idempotency_conflict_returns_typed_409 or idempotency_scope_does_not_cross_reset_to_new_thread" -q` -> pass (`3 passed`)
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts` -> pass (`42 files, 276 tests passed`)
4. `python scripts/ask_phase_a1_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/candidates` -> pass

## Closeoff Decision

Decision: `APPROVED_TO_CLOSE`.

Rationale:

1. A1 backend idempotency scope is implemented and test-covered.
2. Required AQ1 gates are candidate-backed, gate-eligible, and passing.
3. Frozen contract constraints for A1 were preserved.
