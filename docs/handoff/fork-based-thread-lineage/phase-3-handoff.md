# Phase 3 Handoff: Ask Lineage, Lazy Audit Bootstrap, and Generation Consolidation

Status: ready for implementation on 2026-03-25. This is the active continuation brief for the Phase 3 implementation slice.

## What Phases 1 and 2 already completed

- `ChatSession` now persists lineage fields in backend storage
- `integration` storage compatibility is routed to `audit`
- lazy `integration.json -> audit.json` migration exists in `chat_state_store`
- `ThreadLineageService` now exists and is exposed via `app.state.thread_lineage_service`
- storage-backed prompt helpers for later review/split phases now exist
- Phase 2 fixed the legacy-root-source gap so descendant forks can inherit `lineage_root_thread_id` correctly from legacy root audit sessions

Phase 3 should build on those guarantees and should not reopen Phase 1 or Phase 2 scope unless a blocker is discovered.

## Phase 3 scope

Move `ask_planning` onto fork-based lineage, keep audit bootstrap lazy, and migrate frame/spec/clarify generation to reuse `ask_planning`.

In scope:

- `ChatService` adoption of `ThreadLineageService` for `ask_planning` and audit access
- creation of new `ask_planning` threads through `ensure_forked_thread(...)`
- lazy root and child audit bootstrap through lineage helper paths only
- superset thread-level shaping tools on newly created `ask_planning` threads
- generation-service migration so frame/spec/clarify reuse `ask_planning` instead of owning their own thread
- removal of `thread_id` from generation state files while preserving non-thread generation state
- backend unit coverage for ask fork behavior, lazy audit bootstrap, and generation reuse of `ask_planning`

Out of scope:

- execution fork migration
- split migration or review/child true-fork materialization
- review-node cutover from `integration` to `audit`
- removing ask seeding entirely
- wiring local-review, package-review, child-activation, or rollup prompt helpers into chat flows
- deleting `thread_seed_service.py`

## Locked decisions for PR 3

- Root audit stays lazy. Do not bootstrap it in `attach_project_folder()`.
- `ask_planning` must be created with the superset thread-level shaping tools:
  - `emit_frame_content`
  - `emit_spec_content`
  - `emit_clarify_questions`
- Those tools are thread-level configuration, so they must be provided at ask-thread creation time through `ThreadLineageService`.
- Existing ask seeding remains temporarily in place for child handoff safety through Phase 4.
- Ask seeding is removed only after Phase 5 lands first-turn child activation prompt injection from storage.
- Generation services no longer own independent Codex threads in this phase.
- Legacy `ask_planning` sessions are resumed in place. Do not force-reset or re-fork them just to add superset tools.
- Legacy/root audit ancestry remains truthful. Do not invent missing ancestry metadata.

## Required implementation shape

### 1. Adopt lineage helper in `ChatService`

Update `backend/services/chat_service.py` so:

- `ask_planning` uses `thread_lineage_service.ensure_forked_thread(project_id, node_id, "ask_planning", source_node_id=node_id, source_role="audit", fork_reason="ask_bootstrap", workspace_root, base_instructions=..., dynamic_tools=...)`
- new ask threads get ask-planning base instructions plus the superset shaping tools
- audit-thread access uses `thread_lineage_service.resume_or_rebuild_session(...)`
- execution and review/integration workflow ownership stays unchanged in this PR

Required behavioral rules:

- if node audit does not exist yet, ask bootstrap must lazily create or resume it through the lineage helper
- child-node ask access must work even before Phase 5 introduces true review-child audit forks
- legacy ask sessions with existing `thread_id` are resumed as legacy sessions, not replaced

### 2. Keep ask seeding temporarily

Update `backend/services/thread_seed_service.py` carefully:

- do not remove child-focused ask seed behavior yet
- if a guard is added for new ask sessions, it must preserve the existing handoff seed path for child flows
- the goal of Phase 3 is to stop relying on seeds for ancestry, not to remove all ask handoff context yet

Practical rule:

- thread forking provides conversation inheritance
- temporary child ask seeds still provide split/checkpoint handoff context until Phase 5 replaces them with first-turn prompt injection

### 3. Consolidate frame/spec/clarify generation onto `ask_planning`

Update these services:

- `backend/services/frame_generation_service.py`
- `backend/services/spec_generation_service.py`
- `backend/services/clarify_generation_service.py`

Required changes:

- remove per-service `_ensure_gen_thread()` ownership
- read the node `ask_planning` session from `chat_state_store`
- if ask thread is missing, create it through the same lineage-helper path as `ChatService`
- run generation turns on the ask thread id instead of a generation-specific thread id
- remove `thread_id` from `frame_gen.json`, `spec_gen.json`, and `clarify_gen.json`
- keep existing non-thread generation state such as status, revisions, or pending outputs

Required compatibility behavior:

- new ask sessions get superset shaping tools and should support generation directly
- legacy ask sessions may lack those thread-level tools; preserve current fallback parsing behavior instead of trying to rewrite old threads in place

### 4. Keep project-service and split behavior unchanged

Do not change:

- `ProjectService`
- `SplitService`
- `ReviewService`
- execution thread lifecycle

Phase 3 should rely on lazy audit bootstrap, not attach-time bootstrap and not split-time review/child fork materialization.

## Files expected in PR 3

- `backend/services/chat_service.py`
- `backend/services/thread_seed_service.py`
- `backend/services/frame_generation_service.py`
- `backend/services/spec_generation_service.py`
- `backend/services/clarify_generation_service.py`
- `backend/main.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_thread_seeding.py`
- `backend/tests/unit/test_frame_generation_service.py`
- `backend/tests/unit/test_spec_generation_service.py`
- `backend/tests/unit/test_clarify_generation_service.py`

Potentially touched support files if needed:

- `backend/ai/chat_prompt_builder.py` only if ask-planning base-instruction assembly needs a dedicated helper
- generation-state storage helpers if they normalize persisted `thread_id` today

## Acceptance criteria

- `ask_planning` sessions are created through `ThreadLineageService.ensure_forked_thread(...)`
- new ask sessions are configured with the superset shaping tools
- audit access for ask bootstrap uses lineage-helper lazy bootstrap and rebuild behavior
- frame/spec/clarify generation no longer store or own their own `thread_id`
- generation services reuse the ask thread id
- temporary ask seeding still exists for child handoff safety
- no execution, split, or review workflow behavior changes land in this PR

## Suggested verification

- `python -m pytest backend/tests/unit/test_chat_service.py -q`
- `python -m pytest backend/tests/unit/test_thread_seeding.py -q`
- `python -m pytest backend/tests/unit/test_frame_generation_service.py -q`
- `python -m pytest backend/tests/unit/test_spec_generation_service.py -q`
- `python -m pytest backend/tests/unit/test_clarify_generation_service.py -q`
- `python -m pytest backend/tests/unit/test_chat_state_store_multithread.py backend/tests/unit/test_thread_lineage_service.py backend/tests/unit/test_phase2_prompt_builders.py -q`

Phase 3 smoke expectations:

- first ask open on a root or child node creates or resumes audit lazily, then creates `ask_planning` by fork
- new `ask_planning` session metadata contains `forked_from_*` lineage fields and inherited `lineage_root_thread_id`
- generation services use the ask thread and no longer persist a generation-specific `thread_id`
- child ask handoff context still appears through the temporary seed path
