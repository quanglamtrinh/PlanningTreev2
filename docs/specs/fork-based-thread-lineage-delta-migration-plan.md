# Fork-Based Thread Lineage Delta Migration Plan

Status: draft migration plan for review. This plan describes how to move the current implementation to the target model in `fork-based-thread-lineage-state-machine.md`.

## Purpose

This document is a delta plan, not a new product model.

It answers:

- what the codebase does today
- what must change to reach the fork-based lineage model
- which files and services are affected
- what order the work should happen in
- how to handle existing projects and existing persisted thread ids

## Target Reference

The destination architecture is defined in:

- `docs/specs/fork-based-thread-lineage-state-machine.md`

That target model establishes:

- `root.audit` as the only thread created with `thread/start`
- all downstream threads created with `thread/fork`
- review nodes using a canonical `audit` thread in v1
- canonical artifacts persisted to local storage, injected at workflow boundaries by prompt builders
- Codex threads hold conversation context only; no synthetic canonical records are appended to threads

## Recommended Migration Strategy

Use a phased cutover with temporary compatibility layers.

Recommended sequence:

1. Add storage and metadata support first.
2. Introduce fork-aware helper services and prompt builder updates before changing business workflows.
3. Migrate task-node audit and ask lineage first.
4. Migrate execution forking next.
5. Migrate split and review-node lineage after task lineage is stable.
6. Remove legacy `integration` review-thread semantics last.

This order reduces the number of moving pieces changed at once.

## Non-Goals

This migration does not attempt to:

- preserve true historical fork ancestry for already-existing non-root threads
- add multi-split support
- redesign the review detail UX beyond what is needed for the new thread model
- remove all legacy compatibility code in the first rollout

## Current-to-Target Delta Summary

| Area | Current implementation | Target implementation |
|------|------------------------|-----------------------|
| Root thread bootstrap | no canonical root audit bootstrap | root creates `audit` with `thread/start`; project context in base instructions |
| Ask thread creation | `ask_planning` typically `start_thread()` or `resume_thread()` directly | `ask_planning = fork(task.audit)` |
| Execution thread creation | `execution` uses `start_thread()` or `resume_thread()` directly | `execution = fork(task.audit)` |
| Split worker | project-level split thread in `split_service` | split runs on `parent.audit` |
| Review node thread | dedicated `integration` thread | canonical `review.audit` thread |
| Child seeding | seed messages assembled from stores at read time | child `audit = fork(review.audit)`; prompt builder injects child assignment and prior checkpoints from storage |
| Context inheritance | service-built seed context injected into session messages | fork inherits conversation context; prompt builders inject canonical artifacts from local storage at workflow boundaries |
| Recovery | retry with `resume_thread()` or `start_thread()` | re-fork from nearest canonical ancestor; prompt builders re-inject from local storage |

## Biggest Constraint

Existing persisted `thread_id` values were not created under the target lineage model.

That means:

- old `ask_planning`, `execution`, and `integration` threads cannot be made into "true forks" retroactively
- ancestry metadata for old sessions can only start from the migration point forward

Because of that, the migration plan should treat old thread ids as legacy sessions and rebuild forward under the new model.

## Workstreams

### Workstream A: Storage and Session Schema

Primary files:

- `backend/storage/chat_state_store.py`
- `docs/specs/type-contracts-v2.md`
- `frontend/src/api/types.ts`

Required delta:

1. Extend `ChatSession` with lineage metadata:
   - `forked_from_thread_id`
   - `forked_from_node_id`
   - `forked_from_role`
   - `fork_reason`
   - `lineage_root_thread_id`
2. Add safe defaults for legacy sessions.
3. Preserve backward-compatible reads when those fields are missing.
4. Add a review-node compatibility alias so old `integration.json` can migrate to `audit.json`.

Recommended storage behavior:

1. Task nodes continue to use:
   - `chat/{node_id}/audit.json`
   - `chat/{node_id}/ask_planning.json`
   - `chat/{node_id}/execution.json`
2. Review nodes move from:
   - `chat/{review_node_id}/integration.json`
   to:
   - `chat/{review_node_id}/audit.json`

Migration rule for review nodes:

1. If `integration.json` exists and `audit.json` does not, migrate `integration.json` to `audit.json`.
2. During the compatibility window, requests for review-node `integration` should resolve to review-node `audit`.
3. Once frontend and tests are migrated, remove the alias.

### Workstream B: Thread Lineage Helper Layer

Primary files:

- `backend/ai/codex_client.py`
- new helper module, recommended: `backend/services/thread_lineage_service.py`

Why this workstream exists:

Current services call `start_thread()` and `resume_thread()` directly in multiple places.

The migration needs one shared place to handle:

- root bootstrap
- fork creation with prompt builder integration
- resume
- lineage metadata persistence
- missing-thread rebuild policy

Recommended helper API:

- `ensure_root_audit_thread(project_id, node_id, workspace_root)` — start root audit with project context in base instructions
- `ensure_forked_thread(project_id, node_id, thread_role, source_session, fork_reason, workspace_root)` — fork from source and persist lineage metadata
- `resume_or_rebuild_session(project_id, node_id, thread_role, workspace_root)` — resume if thread alive, else re-fork from nearest canonical ancestor
- `rebuild_from_ancestor(project_id, node_id, workspace_root)` — re-fork from nearest surviving canonical ancestor

Goal:

Business services should stop deciding `start` vs `fork` vs `resume` ad hoc. The lineage helper handles thread lifecycle; prompt builders handle context injection from storage.

### Workstream C: Root and Task Audit Bootstrap

Primary files:

- `backend/services/project_service.py`
- `backend/services/chat_service.py`
- `backend/services/thread_seed_service.py`
- `backend/ai/chat_prompt_builder.py`
- `backend/routes/chat.py`

Current delta:

- task nodes have role-based sessions
- review nodes are restricted to `integration`
- seed logic creates inherited context in-memory at read time

Target delta:

1. Root project bootstrap creates `root.audit` with `thread/start` and project context in base instructions.
2. Child task `audit` threads are forked from `review.audit`.
3. `ask_planning` is created by forking from the node's own `audit`.
4. Prompt builders load canonical artifacts from storage and inject them at workflow boundaries, replacing seed-based context assembly.

Seed elimination plan:

All 10 existing seeds are eliminated. Fork inheritance replaces conversation context seeds. Prompt injection from storage replaces canonical data seeds.

| Current seed id | Removal reason | How context is delivered in target model |
|------|------|------|
| `seed:ask_planning:split-item` | remove | conversation context: fork from audit carries prior split-item discussion |
| `seed:ask_planning:checkpoint` | remove | conversation context: fork from audit carries prior checkpoint discussion |
| `seed:audit:split-item` | remove | prompt builder injection: child assignment loaded from review state at child activation boundary |
| `seed:audit:checkpoint` | remove | prompt builder injection: checkpoint summaries loaded from review state at child activation boundary |
| `seed:audit:parent-context` | remove | conversation context: fork from review audit carries parent conversation history |
| `seed:integration:parent-frame` | remove | conversation context: fork from parent audit carries frame discussion history |
| `seed:integration:split-package` | remove | prompt builder injection: split package loaded from tree/review state at rollup boundary |
| `seed:integration:checkpoints` | remove | prompt builder injection: checkpoint summaries loaded from review state at rollup boundary |
| `seed:integration:child-reviews` | remove | prompt builder injection: merged with checkpoints above |
| `seed:integration:goal` | remove | prompt builder injection: rollup goal constructed by rollup prompt builder |

Summary:

- 4 of 10 seeds are eliminated because conversation context from the fork is sufficient
- 6 of 10 seeds are eliminated because prompt builders inject the equivalent data from local storage at specific workflow boundaries

Clarify outcomes:

Clarified answers produced during `ask_planning` are working material. Any clarified outcome that must survive recovery or be consumed by a downstream workflow must be captured in the confirmed frame or the confirmed spec. If a clarified answer is not reflected in frame or spec, it is ephemeral and will not be available after `ask_planning` is re-forked. The spec confirmation step is the gate that ensures all essential shaping outcomes are persisted.

`thread_seed_service.py` retirement plan:

- Remove as the primary inheritance mechanism
- Retain only if any rendering helpers are reused by prompt builders during transition
- Full removal once all prompt builders are self-sufficient

### Workstream D: Finish Task and Execution Forking

Primary files:

- `backend/services/finish_task_service.py`
- `backend/ai/execution_prompt_builder.py`
- `backend/services/execution_gating.py`

Current delta:

- execution thread is started or resumed independently

Target delta:

1. Require spec to be persisted in the node folder.
2. Create `task.execution` by `fork(task.audit)`.
3. Execution prompt builder loads frame and spec from storage and injects them into the execution prompt. This already works correctly in `execution_prompt_builder.py`.
4. Persist lineage metadata on the execution session.

Important:

Fork inherits conversation context from audit. Explicit frame/spec injection from storage remains the execution contract. This is how the codebase already works; the only change is fork instead of start.

### Workstream E: Split Flow Migration

Primary files:

- `backend/services/split_service.py`
- `backend/ai/split_prompt_builder.py`
- `backend/ai/split_context_builder.py`
- `backend/storage/split_state_store.py`

Current delta:

- split uses a project-level split thread

Target delta:

1. Remove the project-level split-thread assumption.
2. Run split turns on `parent.audit`.
3. Split prompt builder loads confirmed frame from storage and injects it into the split prompt.
4. After split is accepted:
   - persist split payload into tree/review state
   - fork `review.audit` from `parent.audit`
   - materialize first child
   - fork `child1.audit` from `review.audit`

Recommended intermediate compatibility step:

1. Keep `split_state_store.active_job` for job tracking.
2. Remove `split_state_store.thread_id` usage only after `parent.audit` lineage is in place.
3. Project-level split thread handling in `split_state_store` is intentionally untouched before this workstream. PR 3 must not modify it.

Known risk:

Because v1 keeps split running on `parent.audit`, split retries and failed attempts can pollute the canonical trunk. Prompt discipline and retry limits must remain strict until a later forked split-worker design exists.

### Workstream F: Review Node Model Conversion

Primary files:

- `backend/services/review_service.py`
- `backend/services/chat_service.py`
- `backend/storage/review_state_store.py`
- `backend/services/snapshot_view_service.py`
- `frontend/src/api/types.ts`

Current delta:

- review nodes only allow `integration`
- integration analysis runs in `integration` thread

Target delta:

1. Review nodes allow only `audit` in v1.
2. `review.audit` becomes the canonical checkpoint and rollup thread.
3. Final rollup analysis runs inside `review.audit` with checkpoint summaries loaded from `review_state.json` by the rollup prompt builder.
4. `review_state.json` remains the structured state source for checkpoints and rollup fields.

Semantic change to encode in code and docs:

- `audit` no longer means "self-review of this node's own implementation"
- `audit` means "canonical review thread for the responsibility scope of this node"

That means:

- task node `audit` reviews the task node's own work
- review node `audit` reviews the direct-child package owned by that review node

### Workstream G: Local Review Promotion and Sibling Activation

Primary files:

- `backend/services/review_service.py`
- `backend/services/execution_gating.py`
- `backend/services/chat_service.py`

Current delta:

- sibling context is manually seeded from checkpoint data

Target delta:

1. Child local review still happens in `child.audit`.
2. On accept:
   - persist summary and `head_sha` to `review_state.json`
3. Only after persistence completes:
   - materialize the next sibling
   - fork `next_child.audit` from `review.audit`
4. The next child's prompt builder loads child assignment and all prior sibling checkpoint summaries from `review_state.json` and injects them into the child's first prompt.

### Workstream H: Recovery and Rebuild

Primary files:

- `backend/services/thread_lineage_service.py`
- `backend/services/chat_service.py`
- `backend/services/finish_task_service.py`
- `backend/services/review_service.py`
- `backend/storage/chat_state_store.py`

Current delta:

- services mostly `resume_thread()` and fall back to `start_thread()`

Target delta:

1. Detect missing upstream app-server thread.
2. Re-fork from the nearest surviving canonical ancestor.
3. Prompt builders inject whatever artifacts the re-forked thread needs from local storage at the next turn.

No canonical record replay is needed because canonical artifacts live in local storage, not in Codex thread messages.

Required local storage for recovery:

- `frame.md` and frame metadata
- `spec.md` and spec metadata
- `review_state.json` (checkpoints, rollup, pending siblings)
- `execution_state.json`
- tree state and split payload records

Recommended rebuild policies:

- `ask_planning`: disposable; re-fork from current task audit
- `execution`: disposable before completion; require explicit retry
- `child.audit`: re-fork from current `review.audit`; prompt builder injects child assignment from storage at next turn
- `review.audit`: re-fork from current `parent.audit`; prompt builder injects checkpoint context from storage at next turn

### Workstream I: Frontend and API Migration

Primary files:

- `frontend/src/api/types.ts`
- `frontend/src/stores/chat-store.ts`
- `frontend/src/features/breadcrumb/BreadcrumbChatView.tsx`
- `frontend/src/features/graph/ReviewGraphNode.tsx`
- `frontend/src/features/node/ReviewDetailPanel.tsx`
- `backend/routes/chat.py`

Current delta:

- frontend still models review-node chat as `integration`
- breadcrumb resolves review-node thread role to `integration`
- graph UI still says "Open integration thread"

Target delta:

1. Change review-node thread role from `integration` to `audit`.
2. During compatibility window:
   - keep `ThreadRole` accepting `integration`
   - map review-node `integration` requests to review-node `audit` on the backend
3. After frontend cutover:
   - remove `integration` from `ThreadRole`
   - remove compatibility alias logic

Compatibility window bounds:

- opens in PR 1 when schema and alias scaffolding land
- closes in PR 6 when frontend cutover removes `integration` from `ThreadRole`

Recommended UX changes:

- keep internal role name `audit`
- show a review-node label such as `Review Audit` or `Checkpoint Audit`
- replace "Open integration thread" with "Open review audit"

### Workstream J: Test Migration

Primary files:

- `backend/tests/unit/test_chat_state_store_multithread.py`
- `backend/tests/unit/test_thread_seeding.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/unit/test_split_service.py`
- `backend/tests/integration/test_chat_api.py`
- `frontend/tests/unit/BreadcrumbChatView.test.tsx`
- other frontend tests touching `ThreadRole`

Test delta by category:

1. Storage tests:
   - add lineage metadata defaults
   - add review `integration.json -> audit.json` migration coverage
2. Chat tests:
   - ask thread forks from audit instead of starting independently
3. Finish task tests:
   - execution thread forks from audit
   - prompt builder loads frame/spec from storage (already tested via execution_prompt_builder)
4. Split tests:
   - split uses parent audit rather than project split thread
   - split prompt builder loads frame from storage
5. Review tests:
   - review node uses `audit` instead of `integration`
   - checkpoint persists to review state before sibling fork
   - rollup prompt builder loads checkpoints from review state
6. Frontend tests:
   - review breadcrumb loads `audit`
   - labels change from integration to review audit

## Existing Project Migration Plan

This is the most delicate part of the rollout.

### Recommended policy

Treat existing sessions as legacy and begin true fork lineage from a migration epoch.

### Recommended behavior for existing persisted data

1. Preserve message history files on disk.
2. Preserve canonical artifact files and review state.
3. Do not trust existing non-root `thread_id` values as fork-accurate ancestry.
4. On first post-migration access:
   - if the session is root audit and can resume cleanly, allow it to remain the lineage root
   - otherwise clear legacy descendant `thread_id` and rebuild descendant lineage from the nearest canonical audit

### Review-node file migration

1. Migrate `integration.json` to `audit.json`.
2. Mark migrated sessions with:
   - `forked_from_role = "audit"`
   - `fork_reason = "review_bootstrap_legacy_migrated"` if exact ancestry is unknown

### Why this is safer than preserving all old thread ids

Because the target model depends on truthful fork ancestry.
Keeping legacy descendant thread ids as if they were true forks would make the lineage metadata misleading and make rebuild logic less reliable.

## Recommended PR Breakdown

### PR 1: Schema and compatibility scaffolding

- extend session schema
- add lineage metadata
- add review `integration -> audit` storage migration and API alias
- no business workflow switch yet
- compatibility window opens here
- rollback: revert schema and alias changes; no business workflow logic depends on them yet

### PR 2: Fork helper service and prompt builder updates

- introduce shared lineage helper
- add tests for `start`, `fork`, `resume`, and rebuild decisions
- update prompt builders to load canonical artifacts from storage at workflow boundaries
- rollback: remove the helper service and restore direct service-level `start_thread()` / `resume_thread()` calls

### PR 3: Root/task audit and ask migration

- root audit bootstrap with project context in base instructions
- ask forks from audit
- remove seed-based context assembly for ask threads
- project-level split thread in `split_state_store` is intentionally untouched here and persists until PR 5
- rollback: revert ask creation to `start_thread()` and remove the root-audit bootstrap call

### PR 4: Execution migration

- execution forks from audit
- execution prompt builder loads frame/spec from storage (already works this way)
- finish task and completion tests updated
- rollback: revert execution creation to `start_thread()` while keeping prompt builder behavior intact

### PR 5: Split migration

- split runs on parent audit
- split prompt builder loads frame from storage
- review audit fork after split persistence
- first child audit fork from review audit
- rollback: restore project-level split thread usage and remove parent-audit split execution

### PR 6: Review-node migration

- replace `integration` workflow with review `audit`
- rollup prompt builder loads checkpoints from review state
- frontend label and route updates
- compatibility window closes here
- rollback: restore `integration` as the review-node role and keep the alias in place

### PR 7: Recovery and cleanup

- rebuild logic (re-fork from ancestor, no replay needed)
- remove obsolete integration-specific code
- retire seed-based inheritance logic and `thread_seed_service.py`
- rollback: rebuild logic is additive; revert falls back to legacy `resume_thread()` / `start_thread()` recovery behavior

## Exit Criteria

The migration is complete when all of the following are true:

1. Root task audit is created with `thread/start`.
2. All new ask threads are forked from task audit.
3. All new execution threads are forked from task audit.
4. Split uses parent audit as the execution source.
5. Review nodes use `audit` rather than `integration`.
6. Sibling activation happens only after checkpoint is persisted to review state.
7. All prompt builders load canonical artifacts from local storage at workflow boundaries.
8. Seed-based context assembly is fully retired.
9. Existing-project compatibility works without losing canonical persisted state.
10. Rebuild logic can recover from lost app-server threads by re-forking and re-injecting from local storage.

## Main Risks

1. Polluting canonical audit with noisy split attempts in v1.
2. Accidentally keeping old descendant `thread_id` values and misrepresenting ancestry.
3. Leaving frontend labels on `integration` while backend semantics have changed to review audit.
4. Partially migrating review-thread semantics and ending up with both `integration` and `audit` active for review nodes.
5. Prompt builders diverging from canonical storage: if a prompt builder loads stale or incomplete data from storage, the injected context will be wrong. Each prompt builder must load from the authoritative storage location and must not cache canonical artifacts across workflow boundaries.

## Confirmed Rollout Decisions

These items are already decided elsewhere in this plan and should not be treated as open questions during implementation:

1. Review-node `integration` is only a temporary compatibility alias.
   Source:
   - compatibility window opens in PR 1 and closes in PR 6
   - see Workstream I and PR breakdown above
2. Existing legacy root audit thread ids may remain the lineage root if they resume cleanly.
   Source:
   - Existing Project Migration Plan
   - if a legacy root audit cannot resume cleanly, rebuild from a fresh canonical root audit instead
