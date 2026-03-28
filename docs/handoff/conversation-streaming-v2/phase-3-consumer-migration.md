# Phase 3: Consumer Migration and Audit Writer Migration

Status: not started.

## Goal

Move critical transcript, metadata, and audit-write consumers onto V2 abstractions before the execution plus audit production cutover.

## In Scope

- transcript consumers that must stop reading V1 session transcript data directly
- metadata and lineage consumers that must go through registry or query abstractions
- immutable audit writer paths that still use V1 append helpers

## Out of Scope

- frontend V2 reducer work
- production cutover
- final deletion of V1 code

## Consumer Targets

Transcript and message-store consumers:

- `backend/services/frame_generation_service.py`
- `backend/services/execution_gating.py`

Metadata and lineage consumers:

- `backend/services/thread_lineage_service.py`
- `backend/services/clarify_generation_service.py`
- `backend/services/spec_generation_service.py`
- `backend/services/split_service.py`

Audit writer targets:

- `backend/services/node_detail_service.py`
- `backend/services/review_service.py`

## Checklist

- route transcript building through `thread_transcript_builder`
- route metadata writes through `thread_registry_service`
- replace direct audit immutable append helpers with `thread_runtime_service.upsert_system_message()` or equivalent V2 abstraction
- migrate frame audit write path in `node_detail_service.py`
- migrate spec audit write path in `node_detail_service.py`
- migrate rollup package audit write path in `review_service.py`
- add tests proving audit items land in V2 snapshot items
- add code-search or static gate proving production paths no longer call `append_immutable_audit_record(...)`

## Verification

- targeted backend tests for migrated consumers
- code search check for legacy immutable audit helper usage
- manual review of production callsites under `backend/services/`

## Exit Criteria

- no production metadata consumer writes metadata outside `thread_registry_service`
- no production audit writer remains on V1 immutable append helpers
- critical transcript consumers no longer depend on legacy transcript schema where V2 abstraction exists

## Artifacts To Produce

- `artifacts/phase-3/consumer-migration-matrix.md`
- `artifacts/phase-3/audit-writer-cutover-check.md`
- `artifacts/phase-3/code-search-evidence.md`
