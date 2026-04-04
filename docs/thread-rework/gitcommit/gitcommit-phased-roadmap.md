# Git Commit Rework Phased Roadmap

Status: planning skeleton for implementation.

Last updated: 2026-04-04.

## 1. Scope and locked decisions

This roadmap assumes the following decisions are frozen:

- all thread interactions are on V3 by-id route surfaces
- no reset-button work is included in this track
- no historical backfill for old nodes; only new writes from rollout forward
- `.planningtree` is tracked/committable
- review prompts must instruct agent to not inspect `.planningtree`
- split action commits immediately after split materialization and records commit on parent node
- execution-node commit points are:
  - `Mark Done from Execution`
  - `Review in Audit`
- `Mark Done from Audit` does not create a new commit
- no-diff action is allowed:
  - no new git commit is created
  - `head_sha` remains equal to `initial_sha`
  - `commit_message` is still persisted as planned message text

## 2. Non-goals

- no migration/backfill of already persisted node state
- no redesign of workflow phase machine itself
- no change to retry semantics already defined in workflow rework specs
- no audit verdict policy changes

## 2A. Current-state gaps (approved baseline)

Gap 1: describe commit fields still read from legacy execution state.

- current behavior: node-detail returns `initial_sha/head_sha/commit_message` from `execution_state`
- impact: split commits and some workflow commits are not represented as a canonical latest commit record in describe

Gap 2: split commit write-path does not persist a full describe metadata record.

- current behavior: split writes `split_commit_sha` and updates `review_state.k0_git_head_sha` when commit exists
- impact: missing explicit `initial_sha`, `commit_message`, and no-diff committed flag for parent-node describe

Gap 3: execution/audit commit helper returns SHA only.

- current behavior: workflow `commit_workspace` returns only resulting SHA
- impact: callers do not persist full metadata tuple (`initial_sha`, `head_sha`, `commit_message`, `committed`)

Gap 4: no-diff semantics are not fully consistent across old/new paths.

- current behavior: core git helper correctly produces no new commit on no-diff, but legacy finish-task path can clear commit message on no-diff
- impact: violates approved rule for this track where planned commit message must still be persisted

Gap 5: split metadata cannot be stored in execution state.

- reason: execution-state presence/status participates in execution gating and shaping freeze decisions
- impact if violated: split could falsely mark node as execution-started

Gap 6: reset endpoint still depends on execution-state SHAs.

- current behavior: reset target uses `execution_state.initial_sha/head_sha`
- scope decision: accepted as known limitation in this track because reset is out-of-scope

## 2B. Workflow examples (must remain true after implementation)

Example 1: split on parent node `2.3`.

- before split commit attempt: `initial_sha = C9`
- after split with diff: `head_sha = C10`, `committed=true`, message persisted
- after split with no diff: `head_sha = C9`, `committed=false`, same planned message persisted
- metadata is recorded on parent node `2.3`

Example 2: `Mark Done from Execution`.

- action commits candidate workspace when diff exists
- no-diff keeps head unchanged
- in both cases describe fields must still have planned message and pre/post sha pair

Example 3: `Review in Audit` commit succeeded but review start failed.

- first attempt produces reviewed commit `C1`
- retry reuses `C1` and does not create `C2`
- latest commit metadata remains stable for that action attempt

## 2C. Approved implementation approach

1. extend workflow state with normalized `latestCommit` metadata block
2. enrich commit helper result to return `initialSha`, `headSha`, `commitMessage`, `committed`
3. write split metadata to parent node workflow state only
4. write execution/audit action metadata to workflow state on commit attempt
5. update node-detail read order: `latestCommit` first, `execution_state` fallback second
6. keep reset route unchanged in this track and document it as out-of-scope
7. add tests for split, mark-done, review-in-audit, no-diff, and retry/idempotency stability

## 3. Commit trigger matrix (authoritative for this track)

| Action | Node kind | Creates new commit when diff exists | Metadata target node | Notes |
|---|---|---:|---|---|
| Split | task node (parent being split) | yes | parent node | commit runs after split projection persists |
| Mark Done from Execution | task node | yes | current task node | sets accepted sha in workflow state |
| Review in Audit | task node | yes | current task node | creates immutable review commit sha |
| Mark Done from Audit | task node | no | none (reuse prior) | accepts existing reviewed commit |

Retry constraint (already locked in workflow docs):

- if `Review in Audit` committed `reviewCommitSha = C1` but review-start failed, retry must reuse `C1` and must not produce `C2`

## 4. Commit metadata contract for Describe tab

Node describe commit section should expose one canonical latest record:

- `initial_sha` (sha before action commit attempt)
- `head_sha` (sha after action, may equal initial when no diff)
- `commit_message` (planned message used for commit attempt)
- optional internal metadata for diagnostics:
  - `source_action` (`split`, `mark_done_from_execution`, `review_in_audit`)
  - `committed` (`true` when new git commit created, else `false`)
  - `recorded_at`

Compatibility rule:

- public `DetailState` field names stay unchanged (`initial_sha`, `head_sha`, `commit_message`)

Storage rule:

- do not overload `execution_state` for split metadata
- use a workflow-owned metadata location so split recording does not mark execution as started

## 5. Data model proposal (phase target)

Add a workflow-owned commit metadata block per node (example shape):

```json
{
  "latestCommit": {
    "sourceAction": "split",
    "initialSha": "abc...",
    "headSha": "def...",
    "commitMessage": "pt(1): split Implement auth",
    "committed": true,
    "recordedAt": "2026-04-04T10:00:00Z"
  }
}
```

Rules:

- update `latestCommit` on each eligible action in commit matrix
- if action is no-diff, set `committed=false`, keep `headSha=initialSha`, keep `commitMessage`
- write atomically with existing workflow state update cycle

## 6. Read-path contract for node-detail

Node detail read order for non-review nodes:

1. workflow-owned `latestCommit` block (new source of truth)
2. fallback to existing `execution_state` fields when new block is missing
3. review nodes continue returning null commit fields

`current_head_sha` behavior remains unchanged (live workspace head probe).

## 7. Phase split and effort estimate

Total effort baseline: 100%.

| Phase | Name | Effort % | Primary owners |
|---|---|---:|---|
| 0 | Contract freeze and schema decision | 10% | BE lead |
| 1 | Workflow store extension + normalization | 14% | BE |
| 2 | Split commit metadata write path | 14% | BE |
| 3 | Execution/Audit commit metadata write path | 20% | BE |
| 4 | Node-detail read-path cutover | 14% | BE + FE |
| 5 | Regression + parity hardening | 16% | QA + BE |
| 6 | Rollout gate and stabilization | 8% | BE + QA |
| 7 | Cleanup and closeout | 4% | BE |

## 8. Detailed phase skeleton

## Phase 0 (10%) - Contract freeze and schema decision

Goals:

- freeze trigger matrix and no-diff semantics
- freeze storage owner (workflow-owned, not execution-state-owned for split)

Checklist:

- finalize docs for trigger matrix and describe contract
- finalize fallback behavior for nodes without new metadata

Exit criteria:

- no open contract ambiguity for implementation start

## Phase 1 (14%) - Workflow store extension + normalization

Goals:

- add normalized `latestCommit` block in workflow state store

Checklist:

- extend store default state and normalization
- preserve backward compatibility when field absent
- add unit tests for normalization and missing/partial payloads

Exit criteria:

- workflow state can persist/read commit metadata safely

## Phase 2 (14%) - Split commit metadata write path

Goals:

- record split commit metadata on parent node at split-time

Checklist:

- capture pre-commit sha and post-action sha
- persist planned commit message even when no diff
- set source action to `split`
- keep existing split behavior and review bootstrap intact

Exit criteria:

- parent node describe shows split commit metadata for new split actions

## Phase 3 (20%) - Execution/Audit commit metadata write path

Goals:

- persist commit metadata for `Mark Done from Execution` and `Review in Audit`

Checklist:

- enrich commit helper return data to include planned message + pre/post sha + committed flag
- update workflow actions to write `latestCommit`
- preserve idempotency semantics (same key -> stable metadata, no duplicate commit)
- preserve review retry reuse semantics for `reviewCommitSha`

Exit criteria:

- execution/audit actions update describe metadata deterministically

## Phase 4 (14%) - Node-detail read-path cutover

Goals:

- read commit fields from workflow-owned metadata first

Checklist:

- update node detail service read order
- keep API field names unchanged
- ensure review-node behavior remains null for commit fields

Exit criteria:

- describe commit section renders from new source for new actions

## Phase 5 (16%) - Regression and parity hardening

Goals:

- lock behavior with end-to-end coverage

Checklist:

- unit tests for:
  - split metadata write
  - execution/audit metadata write
  - no-diff metadata behavior
- integration tests for describe payload after each commit trigger
- regression checks for retry semantics and idempotency

Exit criteria:

- test matrix green on critical flows

## Phase 6 (8%) - Rollout gate and stabilization

Goals:

- deploy safely and monitor metadata consistency

Checklist:

- rollout in staged environments
- track:
  - missing metadata rate for new commit-trigger actions
  - mismatch between `head_sha` in describe and workflow accepted/reviewed sha where applicable
  - retry/idempotency anomalies

Exit criteria:

- stabilization window complete without blocking regression

## Phase 7 (4%) - Cleanup and closeout

Goals:

- finalize ownership and remove temporary compatibility branches where approved

Checklist:

- remove temporary fallback branches no longer needed
- publish closeout notes and residual risks

Exit criteria:

- commit metadata path considered default and operationally stable

## 9. Test matrix baseline

Minimum automated coverage before rollout:

- split with diff -> `committed=true`, sha changes
- split without diff -> `committed=false`, `head_sha==initial_sha`, message persisted
- mark-done-execution with diff/no-diff
- review-in-audit with diff/no-diff
- review-in-audit retry after start failure reuses same reviewed commit
- node detail read fallback when `latestCommit` is absent

## 10. Risks and mitigations

- Risk: split metadata accidentally toggles execution-state gating.
  - Mitigation: keep storage workflow-owned and avoid writing split info into `execution_state`.
- Risk: idempotent retry rewrites metadata unexpectedly.
  - Mitigation: cache/guard action writes by existing idempotency flow.
- Risk: review prompt still scans `.planningtree`.
  - Mitigation: keep explicit prompt constraints and test prompt generation.
