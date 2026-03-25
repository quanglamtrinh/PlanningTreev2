# Phase 4 Handoff: Execution Fork Migration and Local Review Injection

Status: ready for implementation on 2026-03-25. This is the active continuation brief for the Phase 4 implementation slice.

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

Phase 4 should build on those guarantees and should not reopen Phase 3 scope unless a blocker is discovered.

## Phase 4 scope

Fork execution from task audit and inject execution artifact context at the local-review boundary.

In scope:

- `FinishTaskService` adoption of `ThreadLineageService` for `execution`
- creation of new `execution` threads through `ensure_forked_thread(...)`
- preserving execution prompt-builder behavior that already loads frame/spec from storage
- wiring `build_local_review_prompt(...)` into audit chat for post-execution local review
- adding a local-only first-turn boundary marker so execution artifacts are injected only at the opening of local review
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
- The local-review marker is local-only metadata in session storage and must not be written into Codex thread history.
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

- execution completion opens a local-only local-review boundary marker
- the first user-authored audit turn after that marker gets the injected local-review context
- once that turn is consumed, later audit turns revert to the normal audit chat prompt path

### 3. Keep the rest of the workflow unchanged

Do not change:

- `SplitService`
- `ReviewService`
- review-node `integration` semantics
- package-review or child-activation prompt injection
- ask seeding behavior

Phase 4 is limited to execution lineage and local-review boundary injection.

## Files expected in PR 4

- `backend/services/finish_task_service.py`
- `backend/services/chat_service.py`
- `backend/ai/chat_prompt_builder.py`
- `backend/main.py` only if constructor wiring changes are needed
- `backend/tests/unit/test_finish_task_service.py`
- any focused audit-chat tests needed to prove first-turn-only local review injection

Potentially touched support files if needed:

- execution-related helpers if they currently hardcode direct thread lifecycle assumptions
- a session-marker helper if the local-review boundary marker needs normalization logic

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
