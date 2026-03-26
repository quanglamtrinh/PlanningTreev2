# Handoff: Git Task-Checkpoint Implementation

## What to do

Implement Git as a task-checkpoint engine for the execution lifecycle, following the approved plan.

## Required reading

### 1. Feature spec

```
docs/features/git-task-checkpoints.md   — Flows, guardrail rules, SHA domains, state machine
```

### 2. Implementation plan

The full implementation plan is at:
```
C:\Users\Thong\.claude\plans\eager-floating-wilkes.md
```
Contains: architecture, service API, guardrail validation rules, baseline resolution, auto-commit sequence + failure handling, reset sequence, phased implementation, acceptance scenarios, technical risks, critical files reference, implementation checklist.

### 3. Existing code context

```
backend/services/finish_task_service.py   — Existing Finish Task flow (wire git INTO this)
backend/services/split_service.py         — K0 checkpoint creation (add k0_git_head_sha alongside K0)
backend/services/review_service.py        — Checkpoint consumer (NOT modified)
backend/services/execution_gating.py      — Shaping freeze + can_finish_task gating
backend/services/node_detail_service.py   — Detail state enrichment
backend/storage/execution_state_store.py  — Execution state schema
backend/storage/review_state_store.py     — Review state + checkpoint normalization
frontend/src/stores/detail-state-store.ts — Store stubs for initGit/resetWorkspace
frontend/src/features/graph/Sidebar.tsx   — Git init CTA + refresh chain
```

## Progress

| Phase | Name | Status |
|---|---|---|
| 1 | Documentation artifacts | complete |
| 2 | Core git service + error classes | not started |
| 3 | State store + detail state + git_initialized (read model) | not started |
| 4 | Finish Task git integration (write path) | not started |
| 5 | API endpoints (git/init + reset-workspace) | not started |
| 6 | Frontend store wiring + invalidation | not started |
| 7 | Integration tests | not started |

## Key design decisions

1. **SHA mixed format**: K0 stays `sha256:`, execution uses git hex, `k0_git_head_sha` bridges the gap for first-sibling baseline enforcement.

2. **Failed status**: Execution state machine gains `failed` — retryable, not frozen, never reaches review. Prevents fake success when auto-commit fails.

3. **Completion sequencing**: Strict order with "point of no return" after state write. Post-completed errors are best-effort only, never trigger `fail_execution()`.

4. **Contract split**: `commit_if_changed()` is critical (failure = fail execution). `get_changed_files()` is best-effort (failure = log, return []).

5. **Invalidation ownership**: Sidebar owns `initGit → refreshProjects()`. Store calls API only.

6. **Button sync**: Detail panel uses `can_finish_task` (not `git_ready` directly) to stay in sync with graph button. Both derive from `derive_execution_workflow_fields`.

7. **Nested repo prevention**: `init_repo()` calls `check_inside_parent_repo()` first. Subfolder inside parent repo returns `git_initialized = false` via `probe_git_initialized()`.
