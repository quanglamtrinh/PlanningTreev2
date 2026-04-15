# Phase A2 Kickoff Checklist v1

Status: Ready-to-run checklist.

Last updated: 2026-04-14.

## Goal

Run this checklist before writing AQ2 refactor code to avoid governance and closure blockers.

## Checklist

1. Entry markers:
   - confirm `phase_a1_passed` exists in:
     - `phase-a1-backend-ask-idempotency-foundation/close-phase-v1.md`
   - confirm `lane_aware_queue_core_contract_frozen` exists in:
     - `phase-a2-lane-aware-queue-core-refactor/lane-aware-queue-core-contract-freeze-v1.md`
2. Freeze integrity:
   - run `npm run check:ask_migration_freeze`
   - verify output is `PASS`.
3. AQ2 gate harness smoke:
   - generate dry-run source artifacts with:
     - `python scripts/ask_phase_a2_source_evidence.py --source execution_queue_regression_suite --allow-synthetic --self-test`
     - `python scripts/ask_phase_a2_source_evidence.py --source lane_adapter_contract_tests --allow-synthetic --self-test`
     - `python scripts/ask_phase_a2_source_evidence.py --source queue_state_machine_determinism --allow-synthetic --self-test`
   - generate gate report with:
     - `python scripts/ask_phase_a2_gate_report.py --self-test`
   - note: synthetic mode is dry-run only and cannot be used for closure.
   - note: gate report may return exit code `2` in synthetic mode because gates are not closure-eligible.

## Expected Result

If all checklist items pass:

1. governance entry criteria are explicit and machine-checkable.
2. AQ2 evidence and gate-report pipeline is ready before implementation starts.
3. execution-regression-first refactor can proceed with lower risk.
