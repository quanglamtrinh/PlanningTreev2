# Phase 6 Handoff: Review-Node Cutover to Audit

Status: completed on 2026-03-25. This document now serves as the historical brief for the completed Phase 6 implementation slice.

## What landed in Phase 6

- review-node chat semantics now use `audit` end-to-end instead of public `integration`
- `ChatService` now allows review nodes to open only `audit`; review-node audit is always read-only for user chat
- `ReviewService` now persists rollup turns, SSE events, and live-turn tracking in the review node's `audit` session
- rollup prompt assembly no longer depends on seeded system messages; it now uses `build_rollup_prompt_from_storage(...)`
- review rollup thread recovery/bootstrap now goes through `ThreadLineageService.resume_or_rebuild_session(..., "audit", ...)`
- `ChatStateStore` no longer exposes the `integration -> audit` alias; explicit unknown roles now fail instead of silently falling back to `ask_planning`
- lazy `integration.json -> audit.json` migration is still retained for historical data
- review/integration seed constants and builder branches were removed from `thread_seed_service.py`
- review-node breadcrumb routing now resolves to `audit`, the single review header is labeled `Review Audit`, and graph tooltip text now says `Open review audit`
- active contract docs now describe review nodes as `review.audit`, not `review.integration`

## Verification performed

- backend unit tests passed:
  - `backend/tests/unit/test_chat_state_store_multithread.py`
  - `backend/tests/unit/test_thread_readonly.py`
  - `backend/tests/unit/test_thread_seeding.py`
  - `backend/tests/unit/test_review_service.py`
- result: `58 passed in 9.82s`
- backend integration tests passed:
  - `backend/tests/integration/test_chat_api.py`
  - `backend/tests/integration/test_review_api.py`
  - `backend/tests/integration/test_lifecycle_e2e.py`
- result: `34 passed in 19.94s`
- frontend breadcrumb test passed from `frontend/`:
  - `tests/unit/BreadcrumbChatView.test.tsx`
- result: `10 passed`

## Phase 6 scope

Close the temporary review-node `integration` compatibility window, move public/backend review chat semantics to `audit`, switch rollup prompting to storage-backed context, and align UI/contract docs with the new `review.audit` model.

In scope:

- review-node thread validation and read-only behavior in `ChatService`
- review rollup session persistence and SSE stream cutover in `ReviewService`
- removal of public `integration` alias handling from `ChatStateStore`
- removal of review/integration seed code from `thread_seed_service.py`
- frontend `ThreadRole` and review breadcrumb/graph label updates
- contract-doc updates for active thread-role semantics
- backend/unit/integration/frontend tests covering the cutover

Out of scope:

- renaming integration-themed internal helper/module/log symbols
- deleting `thread_seed_service.py` entirely
- broader recovery cleanup outside the Phase 6 review cutover
- gating decoupling away from local session markers

## Locked decisions for PR 6

- review-node public chat role is now `audit`; `integration` is no longer accepted by chat APIs or frontend typing
- review-node audit remains read-only to users; automated rollup writes there internally
- review rollup still uses the "integration rollup" workflow name, but it runs inside `review.audit`
- `integration.json` migration remains for old data only; no new caller should ever depend on the alias again
- review-node audit is not eagerly bootstrapped on breadcrumb read; lifecycle ownership stays with `ReviewService`
- active contract docs must reflect Phase 6 semantics immediately, while historical handoff docs remain unchanged

## Files touched in PR 6

- `backend/storage/chat_state_store.py`
- `backend/services/chat_service.py`
- `backend/services/review_service.py`
- `backend/services/thread_seed_service.py`
- `frontend/src/api/types.ts`
- `frontend/src/features/breadcrumb/BreadcrumbChatView.tsx`
- `frontend/src/features/graph/ReviewGraphNode.tsx`
- `frontend/tests/unit/BreadcrumbChatView.test.tsx`
- `backend/tests/unit/test_chat_state_store_multithread.py`
- `backend/tests/unit/test_thread_readonly.py`
- `backend/tests/unit/test_thread_seeding.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/integration/test_chat_api.py`
- `backend/tests/integration/test_review_api.py`
- `backend/tests/integration/test_lifecycle_e2e.py`
- `docs/specs/type-contracts-v2.md`
- `docs/specs/thread-state-model.md`
- `docs/specs/review-node-checkpoint.md`

## Acceptance criteria achieved

- review backend uses `audit` exclusively for review-node chat sessions
- frontend `ThreadRole` no longer includes `integration`
- review breadcrumb now shows `Review Audit`
- public `thread_role=integration` compatibility is closed
- legacy `integration.json` still migrates forward lazily to `audit.json`

## Follow-on for Phase 7

- route all remaining recovery through `ThreadLineageService`
- delete `thread_seed_service.py`
- rename remaining integration-themed helper/module symbols
- keep only historical-data migration and remove obsolete compatibility scaffolding
