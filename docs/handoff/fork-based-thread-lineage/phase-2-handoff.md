# Phase 2 Handoff: Thread Lineage Helper and Prompt-Builder Prep

Status: ready for implementation after Phase 1 completion.

## What Phase 1 already completed

- `ChatSession` now persists lineage fields in backend storage
- `integration` is now a storage compatibility alias that resolves to `audit`
- lazy `integration.json -> audit.json` migration exists in `chat_state_store`
- frontend `ChatSession` typing and `type-contracts-v2.md` were updated to reflect the new fields and alias behavior

Phase 2 should build on those guarantees and should not reopen Phase 1 scope.

## Phase 2 scope

Implement the shared `ThreadLineageService` and add prompt-builder preparation utilities, without changing workflow ownership yet.

In scope:

- new `backend/services/thread_lineage_service.py`
- prompt-builder helper additions in existing builder modules
- `backend/main.py` wiring to create and expose the new service
- unit tests for lineage-helper behavior and prompt-builder prep as needed

Out of scope:

- switching chat, execution, split, review, or generation services to use the helper
- changing thread creation behavior in `ChatService`, `FinishTaskService`, `SplitService`, or `ReviewService`
- removing seed-based behavior
- frontend changes

## Locked decisions for PR 2

- Root audit remains lazy; do not bootstrap it in `attach_project_folder()`
- `dynamic_tools` and `base_instructions` are thread-level configuration and must be accepted by lineage helper APIs
- Legacy sessions with `thread_id` but no lineage metadata are resumed in place and backfilled with `fork_reason="legacy_resumed"`
- Non-root audit can use temporary `fork_reason="audit_lazy_bootstrap"` until later phases add true upstream forks
- `integration` compatibility remains open in this PR; do not remove alias behavior

## Required implementation shape

### 1. Add `ThreadLineageService`

Create `backend/services/thread_lineage_service.py` with a `ThreadLineageService(storage, codex_client, tree_service)` class.

Required methods:

- `ensure_root_audit_thread(project_id, node_id, workspace_root)`
- `ensure_forked_thread(project_id, node_id, thread_role, source_node_id, source_role, fork_reason, workspace_root, *, base_instructions=None, dynamic_tools=None, writable_roots=None)`
- `resume_or_rebuild_session(project_id, node_id, thread_role, workspace_root)`
- `rebuild_from_ancestor(project_id, node_id, thread_role, workspace_root)`
- `_ensure_audit_exists(project_id, node_id, workspace_root)`

Required behaviors:

- `ensure_root_audit_thread(...)`
  - resume existing root audit when possible
  - otherwise `start_thread()` with project context base instructions
  - persist lineage metadata with `fork_reason="root_bootstrap"` and `lineage_root_thread_id = thread_id`
- `_ensure_audit_exists(...)`
  - if audit session already has `thread_id`, return it unchanged
  - if node is root, delegate to `ensure_root_audit_thread(...)`
  - if node is non-root and audit is missing, `start_thread()` with node context and persist `fork_reason="audit_lazy_bootstrap"`
- `ensure_forked_thread(...)`
  - ensure the source audit/session exists before any fork attempt
  - if the target session already has lineage metadata and `thread_id`, resume it
  - if the target session is legacy (`thread_id` exists but `forked_from_thread_id` is null), resume in place and backfill `fork_reason="legacy_resumed"` without inventing ancestry
  - otherwise fork from source session thread id and persist all fork metadata, including `lineage_root_thread_id`
- `resume_or_rebuild_session(...)`
  - resume existing session when thread exists
  - on missing-thread error, call `rebuild_from_ancestor(...)`
- `rebuild_from_ancestor(...)`
  - root audit -> restart from root bootstrap
  - ask/execution -> rebuild by forking from node audit
  - child audit -> rebuild from `review.audit`
  - review audit -> rebuild from `parent.audit`

Error handling:

- reuse the existing missing-thread detection pattern already used in current chat flow
- do not treat generic Codex errors as rebuild triggers

### 2. Add prompt-builder prep only

Add these helper functions without wiring them into workflow callers yet:

- `build_local_review_prompt(storage, project_id, node_id, user_content)`
- `build_package_review_prompt(storage, project_id, node_id, user_content)`
- `build_child_activation_prompt(storage, project_id, node_id, review_node_id, user_content)`
- `build_rollup_prompt_from_storage(storage, project_id, review_node_id)`
- extend split prompt builder so split service can pass `frame_content` loaded from storage

Expectation:

- these are helper additions only in PR 2
- no service should start calling them until later phases

### 3. Wire service creation in `backend/main.py`

- create `ThreadLineageService` during app startup
- expose it via `app.state.thread_lineage_service`
- do not change downstream service constructors yet unless the change is behavior-neutral and unused until later phases

## Files expected in PR 2

- `backend/services/thread_lineage_service.py` (new)
- `backend/ai/chat_prompt_builder.py`
- `backend/ai/split_prompt_builder.py`
- `backend/ai/integration_rollup_prompt_builder.py`
- `backend/main.py`
- `backend/tests/unit/test_thread_lineage_service.py` (new)

## Acceptance criteria

- Phase 1 lineage fields are used by the helper without any schema changes
- helper methods cover lazy audit bootstrap, legacy detection, fork persistence, and ancestor rebuild decisions
- prompt-builder prep helpers exist with stable signatures for later phases
- app startup exposes `thread_lineage_service`
- no workflow behavior changes yet in chat/execution/split/review/generation services

## Suggested verification

- `python -m pytest backend/tests/unit/test_thread_lineage_service.py -q`
- targeted builder tests if added
- existing Phase 1 test file should still pass after PR 2 changes
