# Phase 4 Handoff: Execution Fork Migration and Local Review Injection

Status: completed on 2026-03-25. This document now serves as the historical brief for the completed Phase 4 implementation slice.

## What landed in Phase 4

- `FinishTaskService` now bootstraps `execution` through `ThreadLineageService.ensure_forked_thread(...)` with `fork_reason="execution_bootstrap"`
- execution session initialization now preserves `forked_from_*`, `fork_reason`, and `lineage_root_thread_id` instead of wiping them with `clear_session(...)`
- `execution_state.json` now tracks `local_review_started_at` and `local_review_prompt_consumed_at`
- `ReviewService.start_local_review(...)` opens the local-review boundary, and `accept_local_review(...)` closes it cleanly if no audit turn consumed it
- task-node audit chat now uses `build_local_review_prompt(...)` only while the local-review boundary is open
- first successful audit turn after execution consumes the local-review boundary; failed/stale turns do not

## Verification performed

- `python -m py_compile` passed for all touched backend files and updated test files
- manual service-layer smoke passed for:
  - execution forking from task audit with persisted lineage metadata
  - first-turn-only local review prompt injection
  - failed-first-turn retry retention of local review context
- targeted pytest remains blocked on this workstation by temp-directory permission errors during tmp-path setup/cleanup, so no green pytest run is recorded for this slice

## What Phases 1 through 3 already completed

- `ChatSession` now persists lineage fields in backend storage
- `integration` storage compatibility is routed to `audit`
- lazy `integration.json -> audit.json` migration exists in `chat_state_store`
- `ThreadLineageService` now exists and is exposed via `app.state.thread_lineage_service`
- storage-backed prompt helpers for later review/split phases now exist, including `build_local_review_prompt(...)`
- `ChatService` now bootstraps task `ask_planning` and `audit` through lineage-helper paths on read and send
- new `ask_planning` threads now use the shared superset shaping tools:
  - `emit_frame_content`
  - `emit_spec_content`
  - `emit_clarify_questions`
- frame/spec/clarify generation now reuse `ask_planning` instead of owning generation-specific Codex threads
- temporary child ask seeding remains intentionally active through Phase 4

Phase 4 built on those guarantees without reopening Phase 3 scope.

## Phase 4 scope

Fork execution from task audit and inject execution artifact context at the local-review boundary.

In scope:

- `FinishTaskService` adoption of `ThreadLineageService` for `execution`
- creation of new `execution` threads through `ensure_forked_thread(...)`
- preserving execution prompt-builder behavior that already loads frame/spec from storage
- wiring `build_local_review_prompt(...)` into audit chat for post-execution local review
- adding local-only first-turn boundary markers in `execution_state.json` so execution artifacts are injected only while the local-review boundary remains open
- backend unit coverage for execution fork behavior and first-turn-only local review injection

Out of scope:

- split migration or review/child true-fork materialization
- review-node cutover from `integration` to `audit`
- package-review, child-activation, or rollup prompt injection
- removing temporary ask seeding
- deleting `thread_seed_service.py`
- changing `ProjectService` attach/init behavior

## Locked decisions for PR 4

- Execution must fork from the current node audit thread with `fork_reason="execution_bootstrap"`.
- Execution thread creation must go through `ThreadLineageService`; do not keep direct `start_thread()/resume_thread()` ownership in `FinishTaskService`.
- Execution prompts continue to source canonical frame/spec artifacts from local storage; Phase 4 is not a prompt-builder rewrite for execution itself.
- Local review prompt injection is boundary-scoped, not persistent session scaffolding.
- The local-review marker is local-only metadata in `execution_state.json` and is not written into Codex thread history.
- Temporary ask seeding remains in place through this phase and is removed only in Phase 5 after child first-turn injection exists.
- Split, review-node lineage, and `integration -> audit` cutover remain untouched in this PR.

## Required implementation shape

### 1. Move execution bootstrap onto the lineage helper

Update `backend/services/finish_task_service.py` so:

- `_ensure_execution_thread(...)` uses `thread_lineage_service.ensure_forked_thread(project_id, node_id, "execution", source_node_id=node_id, source_role="audit", fork_reason="execution_bootstrap", workspace_root, base_instructions=build_execution_base_instructions(), writable_roots=writable_roots)`
- execution recovery uses lineage-helper semantics rather than service-local direct thread lifecycle logic
- the execution session persists lineage metadata for newly forked execution threads

Required behavioral rules:

- execution must always fork from the node audit thread
- if node audit is missing or stale, execution bootstrap must resolve it through the lineage helper first
- this phase must not change split/review behavior while execution is being migrated

### 2. Wire local-review prompt injection at the audit boundary

Update the audit chat flow so:

- when execution has completed and local review is about to begin, audit chat uses `build_local_review_prompt(...)`
- execution artifacts are injected only on the first relevant audit turn after the local-review boundary opens
- later audit turns do not re-inject the same execution bundle repeatedly

Practical rule:

- `ReviewService.start_local_review(...)` opens the local-review boundary by setting markers in `execution_state.json`
- the first successful audit turn while that boundary is open gets the injected local-review context
- failed audit turns leave the boundary open; once a successful turn consumes it, later audit turns revert to the normal audit chat prompt path

### 3. Keep the rest of the workflow unchanged

Do not change beyond local-review marker transitions:

- `SplitService`
- `ReviewService` rollup / integration behavior
- review-node `integration` semantics
- package-review or child-activation prompt injection
- ask seeding behavior

Phase 4 is limited to execution lineage and local-review boundary injection.

## Files touched in PR 4

- `backend/services/finish_task_service.py`
- `backend/services/chat_service.py`
- `backend/services/review_service.py`
- `backend/storage/execution_state_store.py`
- `backend/main.py`
- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_execution_state_store.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/integration/test_chat_api.py`
- `backend/tests/integration/test_review_api.py`

Potentially touched support files if needed:

- none beyond the files listed above

## Acceptance criteria

- `execution` sessions are created through `ThreadLineageService.ensure_forked_thread(...)`
- execution threads fork from node audit and persist lineage metadata
- local review uses `build_local_review_prompt(...)` at the correct audit boundary
- execution artifact context is injected on the first relevant audit turn only
- no split, review-node, or ask-seeding behavior changes land in this PR

## Suggested verification

- `python -m pytest backend/tests/unit/test_finish_task_service.py -q`
- focused audit chat tests covering first-turn-only local review injection
- regression smoke for `backend/tests/unit/test_chat_service.py -q` if audit prompt-path logic changes

Phase 4 smoke expectations:

- finishing a task creates or resumes audit as needed, then forks `execution`
- execution session metadata contains the expected `forked_from_*` lineage fields
- opening audit for local review after execution injects execution context only on the first relevant turn
- later audit turns continue normally without repeated execution artifact injection

If local Windows temp-directory permissions block pytest on this workstation, rerun verification with a workspace-scoped `--basetemp` instead of relying on the default temp root.
