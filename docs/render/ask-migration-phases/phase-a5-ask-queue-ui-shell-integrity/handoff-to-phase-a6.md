# Phase A5 to Phase A6 Handoff

Status: Ready for execution handoff (all AQ5 gates passed).

Date: 2026-04-15.

Source phase: `phase-a5-ask-queue-ui-shell-integrity` (`AQ5`).

Target phase: `phase-a6-recovery-edge-hardening` (`AQ6`).

## 1. Handoff Summary

Phase A5 ask queue UI parity and shell integrity are complete and validated:

1. Ask tab now provides full queue controls through a unified ask queue panel.
2. Legacy A4 ask confirmation strip is removed; confirmation is now handled inside the queue panel.
3. Ask queue actions are lane-explicit and use ask-only store methods:
   - `reorderAskQueued`
   - `sendAskQueuedNow`
   - `retryAskQueued`
4. Ask `send now` follows head-only FIFO UX and is disabled for non-head/non-queued entries.
5. Ask pause reason labels are surfaced in-panel and remain independent from metadata shell/chip rendering.
6. Ask composer queue-first behavior is preserved (disabled only when snapshot unavailable/loading).

## 2. Guarantees Intended for Phase A6

Phase A6 may assume:

1. AQC5 freeze marker and UI shell boundary are implemented:
   - queue panel changes do not remove/hide frame/clarify/spec shell context
   - queue state and shell action-state chips remain separate flows
2. Ask queue UI action surface exists and is stable for recovery/edge-case exercises.
3. Ask queue evidence automation for AQ5 is in place and candidate-contract aligned.
4. Execution queue surface and controls remain parity-safe.
5. Audit lane remains queue-disabled and read-only.

## 3. Canonical Inputs for A6

Governance and contracts:

1. `docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json`
2. `docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json`
3. `docs/render/ask-migration-phases/system-freeze/contracts/aqc6-ask-recovery-reset-contract-v1.md`
4. `docs/render/ask-migration-phases/system-freeze/contracts/aqc5-ask-shell-integrity-contract-v1.md`

A5 closure artifacts:

1. `docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/close-phase-v1.md`
2. `docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_queue_ui_actions_suite.json`
3. `docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_shell_visibility_regression_suite.json`
4. `docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_queue_interaction_smoke.json`
5. `docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/phase-a5-gate-report.json`

Tooling entry points:

1. `scripts/ask_phase_a5_queue_ui_actions_suite.py`
2. `scripts/ask_phase_a5_shell_visibility_regression_suite.py`
3. `scripts/ask_phase_a5_queue_interaction_smoke.py`
4. `scripts/ask_phase_a5_gate_report.py`

## 4. Validation Snapshot

Completed checks:

1. `npm run check:ask_migration_freeze` -> pass.
2. `npm run test:unit --prefix frontend -- threadByIdStoreV3.test.ts BreadcrumbChatViewV2.test.tsx` -> pass.
3. `npm run typecheck --prefix frontend` -> pass.
4. `python scripts/ask_phase_a5_queue_ui_actions_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/candidates/ask_queue_ui_actions_suite-candidate.json --candidate-commit-sha local-check` -> pass.
5. `python scripts/ask_phase_a5_shell_visibility_regression_suite.py --self-test --candidate docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/candidates/ask_shell_visibility_regression_suite-candidate.json --candidate-commit-sha local-check` -> pass.
6. `python scripts/ask_phase_a5_queue_interaction_smoke.py --self-test --candidate docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/candidates/ask_queue_interaction_smoke-candidate.json --candidate-commit-sha local-check` -> pass.
7. `python scripts/ask_phase_a5_gate_report.py --self-test --candidate docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/candidates` -> pass.

## 5. Entry Marker for A6

`phase_a5_passed`

This marker is established by A5 closeout and is ready for A6 preflight entry checks.
