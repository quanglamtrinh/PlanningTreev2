# Phase AQ4 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a4-ask-risk-confirmation-policy.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. phase_a3_passed
1. ask_confirmation_risk_policy_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc4-ask-confirmation-risk-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_risk_policy_tests -> ask_stale_intent_unconfirmed_send_events (lte 0 count)
1. ask_confirmation_transition_suite -> ask_requires_confirmation_transition_failures (lte 0 count)
1. ask_confirmation_noise_audit -> ask_false_positive_confirmation_rate_pct (lte 15 pct)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_risk_policy_tests.json
1. docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_transition_suite.json
1. docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/ask_confirmation_noise_audit.json
1. docs/render/ask-migration-phases/phase-a4-ask-risk-confirmation-policy/evidence/phase-a4-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
