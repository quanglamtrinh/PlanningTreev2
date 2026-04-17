# Phase A6 to Phase A7 Handoff

Status: Ready for execution handoff (all AQ6 gates passed).

Date: 2026-04-15.

Source phase: `phase-a6-recovery-edge-hardening` (`AQ6`).

Target phase: `phase-a7-test-matrix-controlled-enablement` (`AQ7`).

## 1. Handoff Summary

Phase A6 recovery and edge-case hardening is complete and validated:

1. Ask queue reload recovery remains deterministic and loss-safe under persisted hydration.
2. Ask reconnect handling remains duplicate-safe and preserves single-flight send behavior.
3. Ask reset mismatch behavior follows frozen policy:
   - clear queue on ask reset mismatch
   - do not rebind queued entries to a new ask thread id
4. Backend ask reset-by-id now publishes workflow update events so workflow/detail bridges refresh after reset.
5. AQ6 source evidence and gate report automation are in place with candidate eligibility enforcement.

## 2. Guarantees Intended for Phase A7

Phase A7 may assume:

1. Ask recovery paths for reload/reconnect/reset/failure are hardened in runtime.
2. Ask reset policy is deterministic (`clear`, not `rebind`) and validated.
3. Ask route mismatch error classification is lane-safe and queue-safe.
4. AQ6 gates and evidence contracts are stable for rollout-stage acceptance matrix work.
5. Execution queue and audit-lane behavior remain unchanged.

## 3. Canonical Inputs for A7

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc7-ask-rollout-gate-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc6-ask-recovery-reset-contract-v1.md`

A6 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reload_recovery_suite.json`
3. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reconnect_duplicate_guard_suite.json`
4. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reset_policy_suite.json`
5. `docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/phase-a6-gate-report.json`

Tooling entry points:

1. `scripts/ask_phase_a6_reload_recovery_suite.py`
2. `scripts/ask_phase_a6_reconnect_duplicate_guard_suite.py`
3. `scripts/ask_phase_a6_reset_policy_suite.py`
4. `scripts/ask_phase_a6_gate_report.py`

## 4. Validation Snapshot

Completed checks:

1. `npm run check:freeze_all` -> pass.
2. `npm run check:ask_migration_freeze` -> pass.
3. `npm run typecheck --prefix frontend` -> pass.
4. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts BreadcrumbChatViewV2.test.tsx` -> pass.
5. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "ask_reset_by_id_clears_thread_snapshot or ask_reset_by_id_publishes_workflow_update or ask_idempotency_scope_does_not_cross_reset_to_new_thread"` -> pass.
6. `npm run check:ask_phase_a6_evidence` -> pass.

## 5. Entry Marker for A7

`phase_a6_passed`

This marker is established by A6 closeout and is ready for A7 preflight entry checks.
