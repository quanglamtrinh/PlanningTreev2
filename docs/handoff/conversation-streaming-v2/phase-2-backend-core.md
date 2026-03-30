# Phase 2: Canonical Backend Core

Status: completed on 2026-03-28.

## Goal

Implement the backend core for V2 snapshots, projection, registry reconciliation, request ledger behavior, and the new V2 routes.

## In Scope

- `ThreadSnapshotV2` and Python domain types
- thread registry store and service
- thread snapshot store V2
- thread event projector
- thread runtime service
- thread query service
- request ledger service
- V2 chat routes and stream endpoints

## Out of Scope

- production cutover
- frontend main UI adoption
- deletion of V1 code

## Module Targets

- `backend/conversation/domain/types.py`
- `backend/conversation/domain/events.py`
- `backend/conversation/projector/thread_event_projector.py`
- `backend/conversation/storage/thread_snapshot_store_v2.py`
- `backend/conversation/storage/thread_registry_store.py`
- `backend/conversation/services/thread_registry_service.py`
- `backend/conversation/services/request_ledger_service.py`
- `backend/conversation/services/thread_runtime_service.py`
- `backend/conversation/services/thread_query_service.py`
- `backend/conversation/services/thread_transcript_builder.py`
- `backend/conversation/services/workflow_event_publisher.py`
- `backend/routes/chat_v2.py`

## Checklist

- implement Python domain models mirroring the active spec exactly
- implement snapshot read, write, reset, and version bump behavior
- implement registry ownership and snapshot reconciliation rules
- implement first-frame `thread.snapshot` stream behavior
- implement `persist-before-publish`
- implement `conversation.item.upsert` and `conversation.item.patch`
- implement `thread.lifecycle`, `thread.reset`, and `thread.error`
- implement request ledger persistence and stale-on-restart handling
- implement metadata synchronization rules for every metadata-bearing mutation
- implement patch validation and stream mismatch behavior

## Verification

- projector replay against Phase 0 fixtures
- backend unit tests for projector, registry, request ledger, and snapshot store
- integration tests for GET plus SSE open sequence

Current verification landed:

- `python -m py_compile backend/conversation/domain/events.py backend/conversation/domain/types.py backend/conversation/projector/thread_event_projector.py backend/conversation/services/request_ledger_service.py backend/conversation/services/thread_query_service.py backend/conversation/services/thread_registry_service.py backend/conversation/services/thread_runtime_service.py backend/conversation/services/thread_transcript_builder.py backend/conversation/services/workflow_event_publisher.py backend/conversation/storage/thread_registry_store.py backend/conversation/storage/thread_snapshot_store_v2.py backend/routes/chat_v2.py backend/main.py backend/storage/storage.py`
- `python -m pytest backend/tests/unit/test_conversation_v2_stores.py backend/tests/unit/test_conversation_v2_projector.py backend/tests/unit/test_conversation_v2_fixture_replay.py backend/tests/integration/test_chat_v2_api.py -q`
- result: syntax check passed; focused Phase 2 suite passed with `16 passed`

Current implementation landed:

- V2 domain models and envelope helpers
- V2 snapshot and registry stores under `.planningtree/conversation_v2/` and `.planningtree/thread_registry/`
- pure projector with patch validation and `outputFilesReplace`
- request ledger service
- thread query service with ensure-and-read semantics and metadata synchronization
- thread runtime service with internal turn ownership for the additive V2 path
- additive `/v2` routes and separate V2 brokers wired in `backend/main.py`
- focused coverage now also verifies:
  - metadata repair through ensure-and-read publishes a fresh `thread.snapshot`
  - reset publishes `thread.reset` followed by a fresh `thread.snapshot`
  - workflow V2 stream emits wrapped workflow envelopes through the dedicated broker
  - adapter-captured Phase 0 raw-event fixtures replay deterministically through the pure projector with no spec drift

## Exit Criteria

- deterministic snapshot generation from fixtures
- no V2 code path emits `message_created`
- metadata-bearing mutations publish `thread.snapshot`
- stream open sequence proves no event loss between GET and subscribe

All Phase 2 exit criteria are now satisfied.

## Ready for Phase 3

Stable Phase 2 primitives that Phase 3 should build on:

- `thread_snapshot_store_v2`
- `thread_registry_store`
- `thread_event_projector`
- `thread_runtime_service`
- `thread_query_service`
- additive `/v2` route surface and separate V2 brokers

Phase 3 must keep these boundaries intact:

- do not migrate production callers by bypassing `thread_runtime_service`
- do not add any new item mutation path outside `conversation.item.upsert` and `conversation.item.patch`
- do not reopen schema or route contract without first updating the active spec
- do not remove V1 paths during consumer migration; Phase 3 is additive migration only

Phase 3 entry checklist:

- start every consumer migration from a V2 abstraction, not a direct store read
- move audit writers off V1 append helpers instead of creating parallel audit persistence paths
- preserve metadata sync through `thread.snapshot` on any repair or lineage update
- keep Phase 2 artifacts linked from `progress.yaml` as the regression baseline for consumer migration

## Artifacts To Produce

- `artifacts/phase-2/projector-replay-matrix.md`
- `artifacts/phase-2/api-payload-examples.md`
- `artifacts/phase-2/verification-notes.md`
- `artifacts/phase-2/phase-3-entry-checklist.md`
