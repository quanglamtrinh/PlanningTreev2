# Phase 6 Rollback Notes

Status: pending.

Rollback primitive:

- disable `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`

Rollback expectations:

- execution and audit entry behavior returns to the pre-Phase-6 production path
- rehearsal-only behavior remains controlled by the separate rehearsal flag
- no schema rollback is required for `ThreadSnapshotV2` or conversation item contracts

Post-rollback checks:

- finish-task no longer enters the production V2 execution branch
- review-rollup no longer enters the production V2 rollup branch
- `/chat-v2` remains available as the hidden or rehearsal surface until a later cleanup phase
