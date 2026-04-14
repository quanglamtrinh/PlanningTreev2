# Phase AQ2 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a2-lane-aware-queue-core-refactor.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a1_passed
1. lane_aware_queue_core_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc1-ask-queue-core-contract-v1.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc3-ask-send-window-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. execution_queue_regression_suite -> execution_queue_parity_failures (lte 0 count)
1. lane_adapter_contract_tests -> lane_adapter_contract_pass_rate_pct (gte 100 pct)
1. queue_state_machine_determinism -> queue_state_transition_nondeterministic_cases (lte 0 count)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/execution_queue_regression_suite.json
1. docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/lane_adapter_contract_tests.json
1. docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/queue_state_machine_determinism.json
1. docs/render/ask-migration-phases/phase-a2-lane-aware-queue-core-refactor/evidence/phase-a2-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
