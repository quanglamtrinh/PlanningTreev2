# Phase A4 to Phase A5 Handoff

Status: Ready for execution handoff (all AQ4 gates passed).

Date: 2026-04-15.

Source phase: `phase-a4-ask-risk-confirmation-policy` (`AQ4`).

Target phase: `phase-a5-ask-queue-ui-shell-integrity` (`AQ5`).

## 1. Handoff Summary

Phase A4 ask risk-confirmation policy is complete and validated:

1. Ask head risk evaluation is active before send and enforces `queued -> requires_confirmation`.
2. Ask head `requires_confirmation` blocks downstream auto-flush (strict FIFO).
3. Ask lane confirm/discard flows are active and lane-aware:
   - confirm restamps context/timestamp then retries send eligibility
   - discard removes blocked head and retries queue flush
4. Ask hydration preserves `requires_confirmation` across reloads.
5. A4-minimal ask inline confirmation strip is live above composer.

## 2. Guarantees Intended for Phase A5

Phase A5 may assume:

1. Ask runtime confirmation semantics are enforced and deterministic.
2. Ask queue pause reason `requires_confirmation` is available for UI logic.
3. Ask queue entry carries optional `confirmationReason` for reason labels.
4. Execution lane queue behavior is unchanged from A3/A4.
5. Audit lane remains queue-disabled and read-only.

## 3. Canonical Inputs for A5

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc5-ask-shell-integrity-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc4-ask-confirmation-risk-contract-v1.md`

A4 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_risk_policy_tests.json`
3. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_transition_suite.json`
4. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_noise_audit.json`
5. `docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/phase-a4-gate-report.json`

## 4. Validation Snapshot

Completed checks:

1. `npm run check:ask_migration_freeze` -> pass.
2. `npx vitest run tests/unit/threadQueuePolicyAdaptersV3.test.ts tests/unit/threadByIdStoreV3.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx` -> pass.
3. `npm run typecheck --prefix frontend` -> pass.
4. `python scripts/ask_phase_a4_risk_policy_tests.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_risk_policy_tests-candidate.json --candidate-commit-sha local-check` -> pass.
5. `python scripts/ask_phase_a4_confirmation_transition_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_confirmation_transition_suite-candidate.json --candidate-commit-sha local-check` -> pass.
6. `python scripts/ask_phase_a4_confirmation_noise_audit.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates/ask_confirmation_noise_audit-candidate.json --candidate-commit-sha local-check` -> pass.
7. `python scripts/ask_phase_a4_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/candidates` -> pass.

## 5. Entry Marker for A5

`phase_a4_passed`

This marker is established by A4 closeout and is ready for A5 preflight entry checks.
