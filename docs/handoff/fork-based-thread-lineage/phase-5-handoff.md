# Phase 5 Handoff: Split Migration, Review/Child Lineage, and First-Turn Prompt Boundaries

Status: completed on 2026-03-25. This document now serves as the historical brief for the completed Phase 5 implementation slice.

## What landed in Phase 5

- `SplitService` now resolves split execution on `parent.audit` through `ThreadLineageService.resume_or_rebuild_session(...)`
- the project-level split thread model is removed; `split_state_store` no longer persists `thread_id`
- split output now accepts either `emit_render_data(kind="split_result")` tool payloads or raw JSON stdout fallback for legacy audit threads without the split tool
- after split persistence, lineage bootstrap eagerly forks:
  - `review.audit <- parent.audit`
  - `child.audit <- review.audit`
- `ReviewService.accept_local_review(...)` now eagerly forks newly activated sibling audits from `review.audit` best-effort after persistence
- child audit bootstrap failures do not roll back checkpoints, sibling materialization, or accepted reviews
- `review_state.rollup` now tracks:
  - `package_review_started_at`
  - `package_review_prompt_consumed_at`
- `accept_rollup_review(...)` opens the package-review boundary after appending the rollup package record into the parent audit session
- `ChatService` now prioritizes audit prompt selection as:
  - package review boundary
  - local review boundary
  - normal audit chat prompt
- `ChatService` now injects child activation context as a successful-turn boundary for child `ask_planning`, so failed first turns still retry with the same storage-backed manifest/checkpoint context
- temporary `ask_planning` seeding has been removed
- local-review and package-review boundary markers are now consumed before `active_turn_id` is cleared, eliminating a race that could otherwise double-inject first-turn context on fast retries
- later healing of a missing `child.audit` now preserves review-based lineage from `review.audit` whenever review ancestry exists; only non-review-ancestry children still use `audit_lazy_bootstrap`

## Verification performed

- `python -m py_compile` passed for all touched backend files and updated tests
- combined pytest verification passed:
  - `backend/tests/unit/test_split_service.py`
  - `backend/tests/unit/test_review_service.py`
  - `backend/tests/unit/test_chat_service.py`
  - `backend/tests/unit/test_review_state_store.py`
  - `backend/tests/unit/test_thread_seeding.py`
  - `backend/tests/unit/test_node_document_service.py`
  - `backend/tests/unit/test_shaping_freeze.py`
  - `backend/tests/integration/test_split_api.py`
  - `backend/tests/integration/test_node_documents_api.py`
  - `backend/tests/integration/test_chat_api.py`
- result: `135 passed in 26.12s`

## Phase 5 scope

Move split to `parent.audit`, materialize true review/child lineage forks, replace temporary child ask seeding with first-turn storage injection, and introduce package-review boundary markers for parent audit chat.

In scope:

- `SplitService` adoption of `ThreadLineageService` for split preflight and execution-thread resolution
- removal of `split_state_store.thread_id`
- post-persist eager bootstrap of `review.audit` and initial `child.audit`
- sibling activation eager bootstrap in `ReviewService`
- successful-turn-boundary `build_package_review_prompt(...)` and `build_child_activation_prompt(...)` wiring in `ChatService`
- removal of temporary ask seeding after child first-turn injection exists
- tests for package/child boundary behavior and lineage bootstrap

Out of scope:

- review-node semantic cutover from `integration` to `audit`
- replacing rollup generation prompts with the storage-backed rollup prompt builder
- frontend label changes such as `Review Audit`
- deleting `thread_seed_service.py` entirely
- broader recovery cleanup beyond the split/review/chat paths touched here

## Locked decisions for PR 5

- Split must never read or reuse a raw stored project-level split thread id.
- Parent split execution must always go through the lineage helper.
- Persisted tree/review state remains canonical; eager lineage bootstrap is best-effort and must not roll back persisted split/review progress if Codex bootstrap fails.
- Child activation prompt injection replaces ask seeding and is consumed by the first successful child ask turn rather than raw first-turn detection.
- Package review prompt injection is boundary-scoped and must consume its marker only after a successful audit turn.
- Compatibility for review-node `thread_role=integration` remains open in this phase even though the underlying stored session is `audit`.
- The stricter lineage rule applies only to later healing-on-access in `ThreadLineageService`; post-persist eager bootstrap in split/review remains best-effort.

## Files touched in PR 5

- `backend/services/split_service.py`
- `backend/services/review_service.py`
- `backend/services/chat_service.py`
- `backend/services/thread_seed_service.py`
- `backend/services/thread_lineage_service.py`
- `backend/storage/split_state_store.py`
- `backend/storage/review_state_store.py`
- `backend/ai/split_prompt_builder.py`
- `backend/main.py`
- `backend/tests/unit/test_split_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_review_state_store.py`
- `backend/tests/unit/test_thread_seeding.py`
- `backend/tests/unit/test_node_document_service.py`
- `backend/tests/unit/test_shaping_freeze.py`
- `backend/tests/integration/test_split_api.py`
- `backend/tests/integration/test_node_documents_api.py`
- `backend/tests/integration/test_chat_api.py`

## Acceptance criteria achieved

- split no longer depends on a project-level split thread
- `review.audit` and `child.audit` lineage is created through the lineage helper
- newly activated sibling audits fork from `review.audit`
- child activation and package review prompt injection both behave as successful-turn boundaries with retry safety
- temporary ask seeding is removed
- legacy/compatibility flows continue working through the `integration -> audit` storage alias during the Phase 5 window

## Follow-on for Phase 6

- switch review-node semantics from `integration` to `audit` everywhere in backend/UI contracts
- replace rollup prompting with `build_rollup_prompt_from_storage(...)`
- remove `integration` from frontend `ThreadRole`
- rename UI labels and actions to `Review Audit`
