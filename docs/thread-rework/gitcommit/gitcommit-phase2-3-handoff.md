# Git Commit Rework - Phase 2-3 Handoff

Status: implemented.

Date: 2026-04-04.

Owner scope: commit metadata write-path for split + execution/audit actions into `workflow_state.latestCommit`.

## 1. Delivered scope

Phase 2 delivered:

- split write-path now records commit metadata on the parent node (`sourceAction=split`).

Phase 3 delivered:

- `mark_done_from_execution` records commit metadata (`sourceAction=mark_done_from_execution`).
- `review_in_audit` records commit metadata (`sourceAction=review_in_audit`).

Still out of scope (unchanged):

- describe read-path cutover to `latestCommit` (Phase 4+).
- reset behavior rework.
- backfill for old nodes.

## 2. Contract implemented

Metadata target:

- canonical persisted target is `workflow_state.latestCommit`.

Persisted fields:

- `sourceAction` in `{split, mark_done_from_execution, review_in_audit}`
- `initialSha`
- `headSha`
- `commitMessage`
- `committed`
- `recordedAt`

No-diff rule implemented:

- no new git commit is created.
- `headSha == initialSha`.
- `committed=false`.
- `commitMessage` is still persisted.

## 3. Service-level implementation details

### 3.1 Split path

File:

- `backend/services/split_service.py`

Changes:

- added typed return object `SplitCommitResult`.
- `_commit_split_projection(...)` now:
  - captures `initialSha` before commit attempt.
  - builds commit message.
  - calls `commit_if_changed`.
  - returns full metadata tuple for both diff and no-diff.
- `_materialize_split_payload(...)` now:
  - writes `workflow_state.latestCommit` for the parent node when split commit attempt is valid.
  - sets `sourceAction="split"` and `recordedAt=iso_now()`.
  - updates `review_state.k0_git_head_sha` only when `committed=true`.

Compatibility behavior preserved:

- when git checkpoint service is unavailable, workspace is missing, or repo is not initialized:
  - split commit attempt is skipped.
  - `latestCommit` is not written.

### 3.2 Execution/Audit path

File:

- `backend/services/execution_audit_workflow_service.py`

Changes:

- added typed return object `WorkspaceCommitResult`.
- `GitArtifactService.commit_workspace(...)` now returns full metadata instead of SHA-only.
- added helper `_materialize_latest_commit(...)` to standardize state write format.
- `mark_done_from_execution(...)`:
  - uses `commit_result.headSha` as `acceptedSha`.
  - writes `state["latestCommit"]` with `sourceAction="mark_done_from_execution"`.
- `review_in_audit(...)`:
  - uses `commit_result.headSha` as `reviewCommitSha`.
  - writes `state["latestCommit"]` with `sourceAction="review_in_audit"`.

Compatibility behavior preserved:

- mutation idempotency cache behavior remains unchanged.
- public API payload shapes remain unchanged.
- review-cycle creation and execution-run decision updates remain unchanged except using `headSha` from commit metadata object.

## 4. Test coverage added

### 4.1 Unit - split

File:

- `backend/tests/unit/test_split_service.py`

Added assertions:

- diff case: `latestCommit` persisted with `committed=true`, `headSha` is new commit.
- no-diff case: `latestCommit` persisted with `committed=false`, `headSha==initialSha`.
- split target correctness: metadata recorded on parent node.
- `k0_git_head_sha` only overwritten on committed split.

### 4.2 Unit - execution/audit

File:

- `backend/tests/unit/test_execution_audit_workflow_service.py`

Added tests:

- `GitArtifactService.commit_workspace` diff case returns metadata with `committed=true`.
- `GitArtifactService.commit_workspace` no-diff case returns metadata with `committed=false` and stable head.
- `mark_done_from_execution` writes `latestCommit` with correct source/action data.
- `review_in_audit` writes `latestCommit`, and `latestCommit.headSha` matches `reviewCommitSha`.

### 4.3 Integration

File:

- `backend/tests/integration/test_workflow_v2_review_thread_context.py`

Added checks:

- after `review-in-audit`, persisted `workflow_state.latestCommit` exists and matches `reviewCommitSha`.
- after `mark-done-from-execution`, persisted `workflow_state.latestCommit` exists and matches `acceptedSha`.
- retry with same `idempotencyKey` does not create new cycle/record and leaves `latestCommit` stable.

## 5. Verification commands and results

Executed:

- `python -m pytest backend/tests/unit/test_split_service.py backend/tests/unit/test_execution_audit_workflow_service.py -q`
- `python -m pytest backend/tests/integration/test_workflow_v2_review_thread_context.py -q`

Result:

- all tests passed.

## 6. Files changed in this phase

- `backend/services/split_service.py`
- `backend/services/execution_audit_workflow_service.py`
- `backend/tests/unit/test_split_service.py`
- `backend/tests/unit/test_execution_audit_workflow_service.py`
- `backend/tests/integration/test_workflow_v2_review_thread_context.py`

## 7. Known limitations carried forward

- describe tab read-path is still legacy-first in this track; `latestCommit` is not yet wired as the read source.
- reset remains based on legacy execution-state SHA fields in this track.
- no backfill for existing nodes created before this rollout.

## 8. Handoff to Phase 4-5

Phase 4 entry tasks:

- cut node-detail commit read-path to `workflow_state.latestCommit` first, then fallback.
- keep outward field names unchanged (`initial_sha`, `head_sha`, `commit_message`).

Phase 5 regression focus:

- cross-check split/execution/audit/no-diff parity end-to-end.
- verify no idempotency regression under repeated requests and partial failures.
