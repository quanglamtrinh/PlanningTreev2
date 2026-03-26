# Phase 7 Handoff: Recovery Hardening and Final Cleanup

Status: completed on 2026-03-25. This document is the final historical brief for the fork-based thread lineage migration.

## What landed in Phase 7

- `ThreadLineageService` is now the sole production owner of start, fork, resume, and rebuild behavior
- `ChatService` no longer replays seed/system context on session load and no longer keeps a generic raw `start_thread()/resume_thread()` fallback for unsupported interactive roles
- `backend/services/thread_seed_service.py` was deleted
- `backend/tests/unit/test_thread_seeding.py` was deleted
- internal rollup helpers/modules were renamed from `integration_*` to `review_rollup_*`
- review-service internal helpers now use `start_review_rollup()` and `_ensure_review_audit_thread()`
- active specs were updated to describe the shipped fork-based model instead of the old seeded/two-phase audit model

## Verification performed

- backend unit tests passed:
  - `backend/tests/unit/test_chat_service.py`
  - `backend/tests/unit/test_thread_readonly.py`
  - `backend/tests/unit/test_review_service.py`
  - `backend/tests/unit/test_split_service.py`
  - `backend/tests/unit/test_thread_lineage_service.py`
  - `backend/tests/unit/test_phase2_prompt_builders.py`
- result: `102 passed in 38.95s`
- backend integration tests passed:
  - `backend/tests/integration/test_chat_api.py`
  - `backend/tests/integration/test_review_api.py`
  - `backend/tests/integration/test_lifecycle_e2e.py`
- result: `34 passed in 127.72s`

## Phase 7 scope

In scope:

- removing remaining seed-based inheritance code
- removing production-service lifecycle ownership outside `ThreadLineageService`
- renaming stale integration-thread internal symbols to review-rollup terminology
- refreshing active lineage/thread specs and final migration artifacts
- preserving existing compatibility for historical `integration.json -> audit.json` migration only

Out of scope:

- changing lineage policy or rebuild semantics beyond ownership cleanup
- changing product-facing "Integration rollup" workflow terminology
- moving audit-record-based gating out of session messages
- frontend behavior changes

## Locked decisions for PR 7

- seed-based session inheritance is fully retired
- local audit record messages remain valid local annotations and are not treated as seed replay
- `review_rollup_*` is the internal naming standard for rollup helpers/modules
- user-facing/domain wording such as `Integration rollup` remains unchanged where it names Layer 2 review semantics
- active specs reflect the shipped fork-based model; older migration docs remain historical records

## Acceptance criteria achieved

- no production import/reference to `thread_seed_service.py` remains
- no production service outside `ThreadLineageService` calls raw `start_thread()` or `resume_thread()`
- review rollup internal code no longer implies a dedicated `integration` thread model
- active specs no longer describe task audit as a seeded two-phase thread
- rebuild coverage remains in place for supported thread-role / node-kind recovery paths
