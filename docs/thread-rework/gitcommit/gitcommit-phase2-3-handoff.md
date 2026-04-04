# Git Commit Rework - Phase 2-3 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-04.

Owner scope: write-path implementation for split and execution/audit commit actions.

## 1. Goal and boundary recap

Phase 2 target:

- persist parent-node commit metadata at split-time

Phase 3 target:

- persist commit metadata on `Mark Done from Execution` and `Review in Audit`

Out of scope for this handoff:

- node-detail read-path cutover (Phase 4)
- broad regression hardening and rollout gates (Phase 5-6)

## 2. Action-to-metadata requirements

Split:

- capture pre-action sha as `initial_sha`
- set `head_sha` to post-action head (or same sha for no diff)
- persist planned commit message
- set source action `split`

Execution/Audit actions:

- `Mark Done from Execution` -> persist metadata for that action
- `Review in Audit` -> persist metadata for that action
- preserve existing retry/idempotency behavior and reviewed-commit reuse guarantees

No-diff rule:

- `committed=false`
- `head_sha == initial_sha`
- keep planned message

## 3. Implementation checklist (Phase 2-3)

- [ ] extend commit helper return payload to include pre/post sha and committed flag
- [ ] wire split service to write `latestCommit` for parent node
- [ ] wire execution workflow actions to write `latestCommit`
- [ ] keep mutation-cache/idempotency behavior stable
- [ ] add unit tests for diff/no-diff variants across all three trigger actions

## 4. Expected write scope (planned)

- `backend/services/split_service.py`
- `backend/services/execution_audit_workflow_service.py`
- `backend/services/git_checkpoint_service.py` (if helper return shape changes)
- `backend/tests/unit/test_split_service.py`
- `backend/tests/unit/test_execution_audit_workflow_service.py`

## 5. Exit criteria for Phase 2-3

- each trigger action writes deterministic `latestCommit` metadata
- no-diff behavior is deterministic and tested
- retry/idempotency semantics remain compliant with workflow specs
