# Phase AQ6 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a6-recovery-edge-hardening.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a5_passed
1. ask_recovery_reset_contract_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc6-ask-recovery-reset-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_reload_recovery_suite -> ask_reload_recovery_loss_events (lte 0 count)
1. ask_reconnect_duplicate_guard_suite -> ask_reconnect_duplicate_send_events (lte 0 count)
1. ask_reset_policy_suite -> ask_reset_policy_violation_events (lte 0 count)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reload_recovery_suite.json
1. docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reconnect_duplicate_guard_suite.json
1. docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/ask_reset_policy_suite.json
1. docs/render/ask-migration-phases/phase-a6-recovery-edge-hardening/evidence/phase-a6-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
