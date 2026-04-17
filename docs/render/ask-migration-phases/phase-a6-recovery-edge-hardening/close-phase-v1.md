# Phase A6 Closeout v1

Status: Completed.

Date: 2026-04-15.

Phase: `phase-a6-recovery-edge-hardening` (`AQ6`).

## Closure Summary

1. Ask queue recovery edges are hardened for reload, reconnect, reset, and failure handling.
2. Ask reload hydration remains deterministic and queue-safe:
   - persisted ask `sending -> queued`
   - persisted ask `requires_confirmation` preserved
3. Ask reconnect safety remains single-flight and duplicate-safe for queued head dispatch.
4. Ask reset mismatch policy is enforced in runtime:
   - route mismatch (`invalid_request`) clears ask queue
   - cleared queue is persisted (no rebind)
   - stream status enters mismatch-safe error pause state
5. Backend ask reset-by-id behavior is contract-aligned:
   - reset is ask-lane only (`ask_planning`)
   - snapshot is cleared deterministically
   - workflow update event is published for UI bridge refresh
6. AQ6 source evidence automation and gate aggregation are delivered with candidate-backed eligibility checks.

## Contract Marker Reference

1. Governing freeze marker: `ask_recovery_reset_contract_frozen`.
2. Marker source:
   - `docs/render/ask-migration-phases/system-freeze/contracts/aqc6-ask-recovery-reset-contract-v1.md`
3. Entry criteria source:
   - `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json` (`A6.entry_criteria`)

## A6 Gate Evidence

1. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reload_recovery_suite.json`
2. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reconnect_duplicate_guard_suite.json`
3. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reset_policy_suite.json`
4. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/phase-a6-gate-report.json`

## Gate Outcome

1. `AQ6-G1` ask reload recovery loss events: `0.0` (target `<= 0`, pass)
2. `AQ6-G2` ask reconnect duplicate send events: `0.0` (target `<= 0`, pass)
3. `AQ6-G3` ask reset policy violation events: `0.0` (target `<= 0`, pass)

## Validation Snapshot

1. `npm run check:freeze_all` -> pass
2. `npm run check:ask_migration_freeze` -> pass
3. `npm run typecheck --prefix frontend` -> pass
4. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts BreadcrumbChatViewV2.test.tsx` -> pass (`2 files, 66 tests passed`)
5. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "ask_reset_by_id_clears_thread_snapshot or ask_reset_by_id_publishes_workflow_update or ask_idempotency_scope_does_not_cross_reset_to_new_thread"` -> pass (`3 passed`)
6. `python scripts/ask_phase_a6_reload_recovery_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/candidates/ask_reload_recovery_suite-candidate.json --candidate-commit-sha local-check` -> pass
7. `python scripts/ask_phase_a6_reconnect_duplicate_guard_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/candidates/ask_reconnect_duplicate_guard_suite-candidate.json --candidate-commit-sha local-check` -> pass
8. `python scripts/ask_phase_a6_reset_policy_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/candidates/ask_reset_policy_suite-candidate.json --candidate-commit-sha local-check` -> pass
9. `python scripts/ask_phase_a6_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/candidates` -> pass

## Closeoff Decision

Decision: `APPROVED_TO_CLOSE`.

Rationale:

1. AQ6 recovery and reset semantics are implemented and test-covered for frozen scope.
2. Reset policy remains `clear queue on ask reset` and is enforced without rebind behavior.
3. Required AQ6 gate sources are candidate-backed, gate-eligible, and pass all thresholds.
4. Execution queue behavior and audit-lane boundaries remain regression-safe.

## Handoff Marker

`phase_a6_passed`
