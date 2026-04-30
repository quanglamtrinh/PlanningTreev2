# Git Task Checkpoints

## Scope

Git as a task-checkpoint engine for the execution lifecycle. Not a full Git client — only the subset needed for: initializing a repo, validating pre-execution guardrails, auto-committing after execution, surfacing checkpoint info, and resetting the workspace.

## Flows

### 1. Git Init

User initializes a Git repo for their project via the Sidebar CTA.

- `POST /v4/projects/{project_id}/git/init`
- Creates repo with `git init --initial-branch main`, adds `.planningtree/` to `.gitignore`, creates initial commit
- Blocks if project folder is inside an existing parent repo (V1: no nested repos)
- Returns initial commit SHA
- `git_initialized` surfaces on `ProjectSummary` and project snapshot

### 2. Pre-Execution Guardrails

Before Finish Task runs, a set of checks must pass:

| # | Check | Pass Condition | Blocker Message |
|---|---|---|---|
| 1 | Git available | `git --version` exits 0 | "Git is not installed or not on PATH." |
| 2 | Repo exists | `rev-parse --git-dir` exits 0 | "No Git repository found. Initialize Git for this project first." |
| 3 | Repo root match | `--show-toplevel` == project_path | "Git repository root ({actual}) does not match project path ({expected})." |
| 4 | .planningtree not tracked | `ls-files --error-unmatch` exits 1 | ".planningtree/ is tracked by Git. Remove from tracking: git rm -r --cached .planningtree/" |
| 5 | Identity configured | user.name + user.email non-empty | "Git identity not configured. Run: git config user.name '...' && git config user.email '...'" |
| 6 | Working tree clean | `status --porcelain=v1` empty | "Working tree is not clean. Commit or discard changes before running this task." |
| 7 | HEAD matches expected | `rev-parse HEAD` == expected | "HEAD ({actual}) does not match expected baseline ({expected})." |

Checks 1-6 run for every Finish Task. Check 7 runs only when an expected baseline SHA is available from the checkpoint chain.

Checks 1-6 also compute `git_ready` / `git_blocker_message` for the detail-state panel. `can_finish_task` is gated on `git_ready` in both the detail panel and the graph node.

### 3. Auto-Commit After Execution

After the Codex execution turn completes:

1. `git add -A` (`.planningtree/` excluded via `.gitignore`)
2. `git diff --cached --quiet` — if no changes, skip commit
3. `git commit -m "pt({hierarchical_number}): {title}"` (truncated to 72 chars)
4. `git rev-parse HEAD` — capture `head_sha`
5. `git diff --name-status {initial_sha} {head_sha}` — collect `changed_files` (best-effort)

Commit is critical — failure triggers `fail_execution()`. Changed-files collection is best-effort — failure is logged and returns `[]`.

No-diff case: `head_sha = initial_sha`, `commit_message = null`, `changed_files = []`.

### 4. Node Checkpoint Info (Detail State)

The detail-state panel shows:

| Field | Source |
|---|---|
| `initial_sha` | Captured from `git rev-parse HEAD` at execution start |
| `head_sha` | From auto-commit (or = initial_sha if no diff) |
| `current_head_sha` | Live `git rev-parse HEAD` (computed on each detail-state load) |
| `commit_message` | From auto-commit (null if no diff) |
| `changed_files` | `ChangedFileRecord[]` from `git diff --name-status` |
| `task_present_in_current_workspace` | `current_head_sha` is a descendant of `head_sha` |
| `git_ready` | All guardrails 1-6 pass |
| `git_blocker_message` | First failing guardrail message, or null |

### 5. Reset Workspace

Two reset modes via `POST /v4/projects/{project_id}/nodes/{node_id}/reset-workspace`:

- `target: "initial"` — `git reset --hard {initial_sha}` (undo execution changes)
- `target: "head"` — `git reset --hard {head_sha}` (restore execution result)

Guards: no active execution for the project. Target SHA must exist.

Workflow Core V2 execution projections are NOT modified by reset.
`current_head_sha` and `task_present_in_current_workspace` are computed live
from git state.

## SHA Domains

Mixed-format SHA behavior is an explicit design choice:

| Domain | Format | Producer |
|---|---|---|
| Execution: `initial_sha`, `head_sha`, `current_head_sha` | Git commit SHA (40-char hex) | `ExecutionAuditOrchestratorV2` via `GitCheckpointService` |
| Review checkpoints: K0.sha | `sha256:` historical workspace hash | `split_service` via `compute_workspace_sha` |
| Review checkpoints: K1+.sha | Git commit SHA | `WorkflowProgressionService` from accepted workflow state |
| Review: `k0_git_head_sha` | Git commit SHA or null | `split_service` (new, alongside K0) |
| Rollup: `rollup.sha`, `rollup.draft.sha` | `sha256:` historical workspace hash shape | Workflow Core V2 review package state via workspace hashing |

Rule: never use `checkpoints[-1]["sha"]` directly for git operations. Normalize through `_resolve_expected_baseline_sha()` which detects format via `is_git_commit_sha()` and falls back to `k0_git_head_sha`.

## Execution State Machine

Extended statuses: `idle | executing | completed | failed | review_pending | review_accepted`

`failed` is new:
- Allows retry (Finish Task can restart from failed)
- Does NOT freeze shaping (frame/clarify/spec edits remain allowed)
- Does NOT reach review (review only accepts from `completed`)
- Persists `error_message` for diagnostics

## Service Architecture

**`git_checkpoint_service.py`** — Pure git subprocess operations, stateless. All git commands run via `_run_git()` with 30s timeout.

Wired into: `ExecutionAuditOrchestratorV2`, `NodeDetailService`, `ProjectService`, `SnapshotViewService`, and `SplitService`.

## Public Routes

Existing route families (per AGENT_RULES.md — no new route families):

- `POST /v4/projects/{project_id}/git/init` - in `projects.py`
- `POST /v4/projects/{project_id}/nodes/{node_id}/reset-workspace` - in `nodes.py`

## Non-Goals

- Full Git client, staging UI, branch switching, push/pull/sync, PRs
- AI commit message generation
- Nested repo / monorepo subfolder support
- Revert-commit flow (only hard reset)
- Re-execution of previously completed nodes
