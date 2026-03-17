# Phase 6 Cleanup Log

## Purpose
- This file is the canonical removal ledger for Phase 6.3.
- Every compatibility cleanup target must be logged here before removal is considered.
- Every removal must reference exact gate evidence and rollback impact.

## Classification Rules
Every entry must classify the target as one of:
- `transitional_and_removable`
- `transitional_but_blocked`
- `intentionally_permanent_compatibility`
- `uncertain_requires_decision`

## Entry Requirements
Every entry must include:
- removal ID
- target path or behavior
- classification
- replacement path
- enabling gate reference
- rollback impact
- status
- notes on why removal is safe or still blocked

## Cleanup Ledger
| Removal ID | Target Path Or Behavior | Classification | Replacement Path | Enabling Gate | Rollback Impact | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `P6.3-R0` | Placeholder - cleanup inventory not yet populated | `uncertain_requires_decision` | `TBD` | `TBD` | `TBD` | `planned` | Replace this placeholder with real inventory entries before any cleanup work begins. |
