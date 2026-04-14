# Phase AQ5 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a5-ask-queue-ui-shell-integrity.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a4_passed
1. ask_shell_queue_ui_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc5-ask-shell-integrity-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_queue_ui_actions_suite -> ask_queue_ui_action_failures (lte 0 count)
1. ask_shell_visibility_regression_suite -> ask_shell_visibility_regressions (lte 0 count)
1. ask_queue_interaction_smoke -> ask_queue_panel_interaction_success_rate_pct (gte 99 pct)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_queue_ui_actions_suite.json
1. docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_shell_visibility_regression_suite.json
1. docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/ask_queue_interaction_smoke.json
1. docs/render/ask-migration-phases/phase-a5-ask-queue-ui-shell-integrity/evidence/phase-a5-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
