# Phase AQ0 Preflight v1

Status: Frozen implementation preflight.
Date: 2026-04-14.

Phase: phase-a0-contract-freeze-ask-queue.

## 1. Entry Criteria Lock

From docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json:

1. decision_pack_approved
1. ask_queue_contract_scope_frozen

## 2. Required Frozen Inputs

1. docs/render/ask-migration-phases/system-freeze/phase-manifest-v1.json
1. docs/render/ask-migration-phases/system-freeze/phase-gates-v1.json
1. docs/render/ask-migration-phases/system-freeze/contracts/README.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc0-ask-queue-parity-scope-v1.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc1-ask-queue-core-contract-v1.md
1. docs/render/ask-migration-phases/system-freeze/contracts/aqc5-ask-shell-integrity-contract-v1.md

## 3. Gate and Evidence Lock

Phase gate sources (from phase-gates-v1.json):

1. ask_contract_review_checklist -> contract_review_open_blockers (lte 0 count)
1. ask_scope_freeze_audit -> unresolved_scope_items (lte 0 count)
1. ask_arch_signoff_log -> architecture_signoff_count (gte 3 count)

Canonical outputs:

1. docs/render/ask-migration-phases/phase-a0-contract-freeze-ask-queue/evidence/ask_contract_review_checklist.json
1. docs/render/ask-migration-phases/phase-a0-contract-freeze-ask-queue/evidence/ask_scope_freeze_audit.json
1. docs/render/ask-migration-phases/phase-a0-contract-freeze-ask-queue/evidence/ask_arch_signoff_log.json
1. docs/render/ask-migration-phases/phase-a0-contract-freeze-ask-queue/evidence/phase-a0-gate-report.json

Eligibility policy:

1. candidate evidence with gate_eligible=true is required for closure.
2. synthetic evidence with gate_eligible=false is local dry-run only.

## 4. Compatibility Boundaries

1. Ask runtime remains read-only for workspace writes.
2. Execution queue behavior must not regress in this phase.
3. Audit lane remains read-only and queue-disabled.

## 5. Preflight Exit

No open preflight blocker remains once entry criteria, frozen inputs, and gate sources above are locked.
