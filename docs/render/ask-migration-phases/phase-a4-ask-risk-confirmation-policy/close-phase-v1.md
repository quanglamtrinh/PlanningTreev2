# Phase A4 Closeout v1

Status: Completed.

Date: 2026-04-15.

Phase: `phase-a4-ask-risk-confirmation-policy` (`AQ4`).

## Closure Summary

1. Ask stale-intent protection is enabled in runtime flush path:
   - risky ask head transitions `queued -> requires_confirmation`
   - no risky ask entry auto-sends without explicit confirm
2. Ask strict FIFO is preserved:
   - ask head `requires_confirmation` blocks downstream auto-send until resolved
3. Ask lane actions are upgraded for AQ4:
   - `confirmQueued(entryId)` re-qualifies entry by restamping `createdAtMs` + `enqueueContext`, clears confirmation reason, and retries flush immediately
   - `removeQueued(entryId)` can remove blocked ask head and retries flush immediately
4. Ask queue pause-reason surface includes `requires_confirmation`.
5. Ask hydration now preserves `requires_confirmation` (while still normalizing `sending -> queued`).
6. A4-minimal ask UI confirmation strip is added above composer with reason label + `Confirm & send` + `Discard`.
7. Execution queue behavior remains unchanged and regression-safe.

## Contract Marker Reference

1. Governing freeze marker: `ask_confirmation_risk_policy_frozen`.
2. Marker source:
   - `docs/render/ask-migration-phases/system-freeze/contracts/aqc4-ask-confirmation-risk-contract-v1.md`
3. Entry criteria source:
   - `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json` (`A4.entry_criteria`)

## A4 Gate Evidence

1. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_risk_policy_tests.json`
2. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_transition_suite.json`
3. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_noise_audit.json`
4. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/phase-a4-gate-report.json`

## Gate Outcome

1. `AQ4-G1` ask stale-intent unconfirmed send events: `0.0` (target `<= 0`, pass)
2. `AQ4-G2` ask requires-confirmation transition failures: `0.0` (target `<= 0`, pass)
3. `AQ4-G3` ask false-positive confirmation rate: `9.5` (target `<= 15`, pass)

## Validation Snapshot

1. `npm run check:ask_migration_freeze` -> pass
2. `npx vitest run tests/unit/threadQueuePolicyAdaptersV3.test.ts tests/unit/threadByIdStoreV3.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx` -> pass (`3 files, 66 tests passed`)
3. `npm run typecheck --prefix frontend` -> pass
4. `python scripts/ask_phase_a4_risk_policy_tests.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_risk_policy_tests-candidate.json --candidate-commit-sha local-check` -> pass
5. `python scripts/ask_phase_a4_confirmation_transition_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_confirmation_transition_suite-candidate.json --candidate-commit-sha local-check` -> pass
6. `python scripts/ask_phase_a4_confirmation_noise_audit.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_confirmation_noise_audit-candidate.json --candidate-commit-sha local-check` -> pass
7. `python scripts/ask_phase_a4_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates` -> pass

## Closeoff Decision

Decision: `APPROVED_TO_CLOSE`.

Rationale:

1. AQ4 stale-intent protection is implemented and test-covered.
2. Required AQ4 gate sources are candidate-backed, gate-eligible, and pass.
3. Ask strict FIFO + explicit confirm semantics are enforced in runtime and reflected in UI.
4. Execution queue parity boundary is preserved.

## Handoff Marker

`phase_a4_passed`
