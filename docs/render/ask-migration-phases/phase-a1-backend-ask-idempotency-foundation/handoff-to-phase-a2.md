# Phase A1 to Phase A2 Handoff

Status: Ready for execution handoff (all AQ1 gates passed).

Date: 2026-04-15.

Source phase: `phase-a1-backend-ask-idempotency-foundation` (`AQ1`).

Target phase: `phase-a2-lane-aware-queue-core-refactor` (`AQ2`).

## 1. Handoff Summary

Phase A1 idempotency foundation is complete and validated:

1. Ask `start_turn` is idempotent when `metadata.idempotencyKey` is present.
2. Replay with same key and same normalized text returns cached accepted payload without creating duplicate turns.
3. Replay with same key and different normalized text returns typed `409` conflict.
4. Key-missing requests retain legacy non-idempotent behavior.
5. Canonical AQ1 evidence is candidate-backed and gate-eligible.

## 2. Guarantees Intended for Phase A2

Phase A2 may assume:

1. Ask duplicate start-turn protection is available and deterministic.
2. Cache retention policy is fixed for A1 baseline (`20m TTL`, `256` max entries, prefix-scoped prune).
3. A1 did not alter execution queue policy/state machine, so A2 starts from existing execution behavior baseline.
4. Ask runtime remains read-only for workspace writes.

## 3. Canonical Inputs for A2

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc1-ask-queue-core-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md`

A1 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_idempotency_integration.json`
3. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_retry_replay_suite.json`
4. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/ask_start_turn_latency_probe.json`
5. `docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/phase-a1-gate-report.json`

## 4. Validation Snapshot

Completed checks:

1. `python -m pytest backend/tests/unit/test_thread_runtime_service_v3.py -q` -> pass.
2. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "idempotent_replay_avoids_duplicate_turn_creation or idempotency_conflict_returns_typed_409 or idempotency_scope_does_not_cross_reset_to_new_thread" -q` -> pass.
3. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts` -> pass.
4. `python scripts/ask_phase_a1_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a1-backend-ask-idempotency-foundation/evidence/candidates` -> pass.

## 5. Entry Marker for A2

`phase_a1_passed`

This marker is established by A1 closeout and is ready for A2 preflight entry checks.
