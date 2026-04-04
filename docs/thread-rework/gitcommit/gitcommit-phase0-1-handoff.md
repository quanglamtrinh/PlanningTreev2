# Git Commit Rework - Phase 0-1 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-04.

Owner scope: freeze contract and prepare workflow-state data model extension for commit metadata.

## 1. Goal and boundary recap

Phase 0 target:

- freeze action trigger matrix and describe metadata contract

Phase 1 target:

- implement workflow-owned `latestCommit` schema + normalization

Out of scope for this handoff:

- split/action write-path implementation
- node detail read-path cutover
- rollout gate work

## 2. Locked decisions to carry into implementation

- no reset work in this track
- no backfill; only forward writes after deployment
- `.planningtree` remains committable
- review prompts must exclude `.planningtree` scanning
- no-diff actions still persist planned `commit_message`
- split metadata must not use `execution_state`

## 3. Implementation checklist (Phase 0-1)

- [ ] freeze docs for trigger matrix and no-diff semantics
- [ ] add `latestCommit` block in workflow state default payload
- [ ] normalize read/write for partial or invalid commit metadata values
- [ ] keep backward compatibility when `latestCommit` absent
- [ ] add store unit tests for schema normalization

## 4. Expected write scope (planned)

- `backend/storage/workflow_state_store.py`
- `backend/tests/unit/*workflow_state*`
- `docs/thread-rework/gitcommit/*`

## 5. Exit criteria for Phase 0-1

- contract decisions are documented and unchanged
- workflow state persists/reads `latestCommit` safely
- no regression on existing workflow-state consumers
