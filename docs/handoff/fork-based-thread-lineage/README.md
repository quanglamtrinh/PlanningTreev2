# Fork-Based Thread Lineage Migration Plan

Status: Phase 5 complete, Phase 6 next. This document is the working implementation plan that translates the fork-based lineage specs into a seven-phase rollout that can be executed incrementally.

Primary specs:

- `docs/specs/fork-based-thread-lineage-state-machine.md`
- `docs/specs/fork-based-thread-lineage-delta-migration-plan.md`

## Current Handoff State

- Phase 1 completed on 2026-03-25
- Phase 2 completed on 2026-03-25
- Phase 3 completed on 2026-03-25
- Phase 4 completed on 2026-03-25
- Phase 5 completed on 2026-03-25
- Phase 6 / PR 6 is the next intended implementation slice
- Phase 3 verification completed with targeted backend unit tests for ask bootstrap, ask seeding retention, generation reuse of `ask_planning`, plus targeted chat API smoke coverage
- Phase 4 verification completed with `py_compile` on touched backend/test files plus manual service-layer smoke for execution fork lineage, first-turn-only local review injection, and failed-first-turn retry retention
- Phase 5 verification completed with `py_compile` plus combined unit/integration pytest coverage across split/review/chat touched areas: `135 passed`
- Post-review cleanup aligned the execution integration-test fake with `fork_thread()` and corrected Phase 4 historical docs so they describe the boundary markers as living in `execution_state.json`
- `docs/handoff/fork-based-thread-lineage/phase-5-handoff.md` now serves as the historical brief for the completed PR 5 slice
- `docs/handoff/fork-based-thread-lineage/phase-4-handoff.md` now serves as the historical brief for the completed PR 4 slice
- `docs/handoff/fork-based-thread-lineage/phase-3-handoff.md` now serves as the historical brief for the completed PR 3 slice

## Context

The current thread model creates threads through `start_thread()` and `resume_thread()` and reconstructs inheritance with seed messages from `thread_seed_service.py`. That model does not mirror task lineage and makes recovery fragile.

The target model uses `fork_thread()` so thread inheritance mirrors task inheritance. Canonical artifacts such as frame, spec, execution state, split packages, checkpoints, and rollup results remain in local storage and are injected into prompts at workflow boundaries. Codex threads hold conversation context only.

An additional current-state gap is that frame, spec, and clarify generation each maintain their own Codex thread in generation state files. In the target model, those generation flows run on `ask_planning` instead of owning separate threads.

## Resolved Blockers

### Blocker 1: generation on `ask_planning`

`ask_planning` will be created with a superset thread-level tool set that includes:

- `emit_frame_content`
- `emit_spec_content`
- `emit_clarify_questions`

This is required because the current Codex client only accepts `base_instructions` and `dynamic_tools` at thread creation time, not per turn. Generation services will therefore reuse the `ask_planning` thread instead of trying to attach per-turn tools later.

Implications:

- new `ask_planning` sessions must be created through the lineage helper with the superset tool set
- frame, spec, and clarify generation services no longer persist their own `thread_id`
- legacy `ask_planning` sessions created before the superset-tool rollout are resumed in place and continue to rely on current stdout fallback parsing until the session is rebuilt or reset

### Blocker 2: temporary ask seeding

Ask-thread seeding is retained temporarily for child handoff safety. It is not removed in the first ask-lineage PR.

Rules:

- keep existing child-focused ask seeds through Phase 4
- remove ask seeding only after Phase 5 wires first-turn child activation prompt injection from storage
- do not remove the ask seed path earlier, because pre-Phase-5 child flows still need split/checkpoint handoff context

### Blocker 3: split must always use the lineage helper

Split may never assume `parent.audit` already exists or manually resume a raw stored thread id.

Rules:

- split must resolve `parent.audit` only through `ThreadLineageService`
- the lineage helper is responsible for lazy bootstrap, resume, or rebuild
- once split moves to `parent.audit`, `split_state_store.thread_id` is removed completely

## Phase Summary

### Phase 1 / PR 1: Schema and compatibility scaffolding

Goal:

- extend `ChatSession` with lineage metadata
- migrate review chat storage from `integration.json` toward `audit.json`
- open a compatibility window without changing workflow behavior

Changes:

- add `forked_from_thread_id`, `forked_from_node_id`, `forked_from_role`, `fork_reason`, and `lineage_root_thread_id` to backend session defaults and normalization
- add lazy `integration.json -> audit.json` migration in `chat_state_store`
- route `thread_role="integration"` to `audit` in `read_session()`, `write_session()`, and `clear_session()` before role validation
- remove `"integration"` from the storage-valid role set so new writes cannot recreate `integration.json`
- extend frontend `ChatSession` typing with the five lineage fields
- document the new fields and alias behavior in `type-contracts-v2.md`

Tests:

- lineage fields round-trip and default correctly
- `integration` read/write/clear alias resolves to `audit`
- lazy migration is idempotent and `audit` wins if both files exist

Rollback:

- revert lineage fields and compatibility alias; no workflow logic depends on them yet

### Phase 2 / PR 2: Thread lineage helper and prompt-builder prep

Goal:

- introduce one shared helper for thread lifecycle decisions
- prepare prompt builders needed by later phases
- keep workflow callers unchanged in this PR; Phase 2 is helper/prep only

Add `ThreadLineageService` with these responsibilities:

- `ensure_root_audit_thread(project_id, node_id, workspace_root)`
- `ensure_forked_thread(project_id, node_id, thread_role, source_node_id, source_role, fork_reason, workspace_root, *, base_instructions=None, dynamic_tools=None, writable_roots=None)`
- `resume_or_rebuild_session(project_id, node_id, thread_role, workspace_root)`
- `rebuild_from_ancestor(project_id, node_id, thread_role, workspace_root)`
- `_ensure_audit_exists(project_id, node_id, workspace_root)`

Behavioral rules:

- root audit is started lazily with project context
- missing non-root audit may be temporarily bootstrapped with `fork_reason="audit_lazy_bootstrap"` until a true upstream fork exists
- legacy sessions with `thread_id` but no lineage metadata are resumed in place and backfilled with `fork_reason="legacy_resumed"`
- root legacy audit backfill also sets `lineage_root_thread_id = thread_id`
- non-root legacy sessions keep `forked_from_* = null` rather than inventing ancestry

Prompt-builder prep:

- add `build_local_review_prompt(...)`
- add `build_package_review_prompt(...)`
- add `build_child_activation_prompt(...)`
- add `build_rollup_prompt_from_storage(...)`
- extend split prompt helpers so split service can pass confirmed frame content from storage

Tests:

- lineage helper unit tests for root bootstrap, fork creation, lazy audit bootstrap, legacy backfill, and rebuild decisions by thread role

Rollback:

- remove the helper service and revert to direct service-level lifecycle calls

### Phase 3 / PR 3: Ask lineage, lazy audit bootstrap, and generation-service consolidation

Goal:

- move `ask_planning` to fork from node audit
- keep root audit bootstrap lazy, not attach-time
- migrate frame/spec/clarify generation to reuse `ask_planning`

Changes:

- do not change `ProjectService`; root audit remains lazy on first access
- update `ChatService` so `ask_planning` uses `ThreadLineageService.ensure_forked_thread(..., source_role="audit", fork_reason="ask_bootstrap")`
- update audit-thread access to use `resume_or_rebuild_session()`
- create new `ask_planning` sessions with the superset shaping tools and ask-planning base instructions
- keep ask seeding temporarily in place for child handoff safety
- remove generation-thread creation from frame/spec/clarify generation services
- generation services read or lazily create the node's `ask_planning` session and reuse its thread id
- remove `thread_id` from `frame_gen.json`, `spec_gen.json`, and `clarify_gen.json`, while keeping other generation state fields

Tests:

- ask now forks from audit
- root or child ask access triggers lazy audit bootstrap if needed
- frame/spec/clarify generation uses the ask thread rather than service-owned generation threads
- old ask sessions still function through stdout fallback parsing

Rollback:

- revert ask creation to direct `start_thread()`
- restore independent generation threads

### Phase 4 / PR 4: Execution fork migration and local-review injection

Status:

- completed on 2026-03-25
- execution now forks from task audit through `ThreadLineageService`
- execution session resets preserve lineage metadata instead of wiping `forked_from_*`
- local review now uses execution-state boundary markers and injects `build_local_review_prompt(...)` on the first relevant audit turn only

Goal:

- fork execution from task audit
- inject execution artifact context at the local-review boundary

Changes:

- update `FinishTaskService` so execution uses `ensure_forked_thread(..., thread_role="execution", source_role="audit", fork_reason="execution_bootstrap", base_instructions=build_execution_base_instructions(), writable_roots=...)`
- keep execution prompt builder contract unchanged: frame and spec still come from storage
- wire `build_local_review_prompt(...)` into audit chat when local review first opens after execution completion
- add local-only boundary markers in `execution_state.json` and inject execution context only until the first successful audit turn consumes that boundary

Tests:

- execution forks from audit
- local review injects execution context on the first relevant audit turn only

Rollback:

- revert execution to direct thread start/resume and remove local-review boundary injection

### Phase 5 / PR 5: Split migration, true review/child forks, and child/package first-turn injection

Status:

- completed on 2026-03-25
- split now resolves `parent.audit` through `ThreadLineageService`
- split/review now eagerly bootstrap review/child audit lineage best-effort after persistence
- package-review and child-activation prompts now inject only on the first relevant successful turn
- temporary ask seeding has been removed

Goal:

- move split execution onto `parent.audit`
- establish true review and child lineage forks
- replace temporary child ask seeding with first-turn injection from storage

Changes:

- `SplitService` must resolve `parent.audit` through `ThreadLineageService.resume_or_rebuild_session(...)`
- split no longer stores or reads a project-level split thread id
- after split persistence:
  - fork `review.audit` from `parent.audit`
  - materialize the first child
  - fork `child.audit` from `review.audit`
- sibling activation in `ReviewService` must fork every newly materialized child audit from `review.audit`
- remove `thread_id` from `split_state_store`
- wire `build_child_activation_prompt(...)` into the first `ask_planning` turn for a child node, gated by there being no prior non-system ask messages
- wire `build_package_review_prompt(...)` into the parent audit package-review boundary using a local-only first-turn marker
- remove temporary ask seeding after first-turn child injection is active

Notes:

- audit sessions created earlier via `audit_lazy_bootstrap` are not rewritten into fake fork ancestry
- once true review-based forks exist, newly activated children must use real fork lineage

Tests:

- split runs on parent audit
- review audit and first child audit are forked correctly
- sibling activation forks next child audit from review audit
- child activation and package review prompts inject the right artifacts on first turn only

Rollback:

- restore the project-level split thread model and re-enable temporary child ask seeding

### Phase 6 / PR 6: Review-node cutover from `integration` to `audit`

Goal:

- complete the review-node semantic switch from `integration` to `audit`
- close the compatibility window

Backend changes:

- review nodes only allow `audit`
- remove the `integration` read-only branch from `ChatService`
- switch `ReviewService` session access from `integration` to `audit`
- replace integration-seeded rollup prompting with `build_rollup_prompt_from_storage(...)`
- use lineage-helper recovery for `review.audit`
- remove integration seed constants and builders
- remove the compatibility alias from `chat_state_store` public methods
- keep lazy `integration.json -> audit.json` migration permanently for old data

Frontend changes:

- remove `'integration'` from `ThreadRole`
- map review breadcrumb routes to `'audit'`
- rename the review header label to `Review Audit`
- rename graph actions from `Open integration thread` to `Open review audit`

Tests:

- backend review chat and rollup paths use `audit`
- frontend labels and role routing reflect `Review Audit`

Rollback:

- restore integration compatibility and revert frontend labels

### Phase 7 / PR 7: Recovery hardening and cleanup

Goal:

- finish recovery behavior
- remove seed-based inheritance code
- leave a clean post-migration baseline

Changes:

- route all remaining thread recovery through `ThreadLineageService`
- delete `thread_seed_service.py`
- remove seed-insertion calls from chat and review paths
- rename integration-specific rollup helpers to review-audit terminology
- keep `integration.json -> audit.json` migration for historical data

Deferred cleanup:

- execution/package gating still uses local audit-record markers in session JSON
- those markers are local-only and do not break the fork model
- migrating that gating to dedicated state-file fields is explicitly deferred until after lineage migration

Tests:

- rebuild paths by node kind and thread role
- removal of seed-service imports and usage

Rollback:

- additive only; revert falls back to the Phase 6 baseline

## Sequencing Constraints

Ordered dependency graph:

- Phase 1 before Phase 2: lineage fields and compatibility scaffolding must exist before the helper can persist metadata
- Phase 2 before Phases 3, 4, and 5: the lineage helper is the foundation for lazy bootstrap, legacy handling, and fork creation
- Phase 3 before Phase 4: execution must fork from audit only after ask/audit bootstrap is stable
- Phase 3 before Phase 5: split must rely on a working audit bootstrap path before review and child forks are introduced
- Phase 5 before Phase 6: review audit lineage must exist before review nodes formally switch away from `integration`
- Phase 6 before Phase 7: remove the compatibility alias only before retiring seed-based inheritance completely

## Verification

After each phase:

1. Backend unit tests: `cd backend && python -m pytest tests/unit/ -x -q`
2. Frontend tests: `cd frontend && npx vitest run`
3. Phase-specific smoke checks:
   - Phase 1: `integration` reads and writes land in `audit.json`; lineage defaults load correctly
   - Phase 3: ask access forks from audit; generation services reuse ask; child ask still receives handoff context
   - Phase 4: Finish Task forks execution; local review gets execution artifact injection on first turn
   - Phase 5: split always resolves parent audit through the lineage helper; review and child audits fork correctly; first-turn child injection replaces temporary ask seeding
   - Phase 6: review nodes use `audit.json`; UI shows `Review Audit`
   - Phase 7: deleting a session file and re-opening the thread triggers rebuild from the correct ancestor

## Companion Tracking Artifact

Use `docs/handoff/fork-based-thread-lineage/progress.yaml` as the implementation tracker for phase status, notes, blockers, and acceptance progress. Update it at the start and end of each phase PR.

Use `docs/handoff/fork-based-thread-lineage/phase-5-handoff.md` as the active continuation artifact for the next implementation slice. Keep older phase handoff docs as historical implementation records.
