# Phase 2: Canonical Backend Core

Status: not started.

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

## Exit Criteria

- deterministic snapshot generation from fixtures
- no V2 code path emits `message_created`
- metadata-bearing mutations publish `thread.snapshot`
- stream open sequence proves no event loss between GET and subscribe

## Artifacts To Produce

- `artifacts/phase-2/projector-replay-matrix.md`
- `artifacts/phase-2/api-payload-examples.md`
- `artifacts/phase-2/verification-notes.md`
