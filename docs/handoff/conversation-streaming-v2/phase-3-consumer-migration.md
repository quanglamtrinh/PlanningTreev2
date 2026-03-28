# Phase 3: Consumer Migration and Audit Writer Migration

Status: completed on 2026-03-28.

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

## Delivered Changes

- `frame_generation_service.py` now routes transcript prompt history through `ThreadTranscriptBuilder.build_prompt_messages(...)`
- `thread_transcript_builder.py` now acts as the mixed-mode transcript facade:
  - `ask_planning` prompt history reads legacy session messages
  - `audit` and `execution` prompt history read canonical V2 snapshot items
- `execution_gating.py` now checks audit markers V2-first by canonical item id and keeps a temporary V1 fallback in the same helper
- immutable audit writer callsites in `node_detail_service.py` and `review_service.py` now write canonical V2 system messages through `ConversationSystemMessageWriter`
- `thread_lineage_service.py` now writes lineage metadata registry-first through `ThreadRegistryService` while preserving legacy session-shaped return values to callers
- `main.py` now wires `ThreadRegistryService` into `ThreadLineageService` and keeps `ConversationSystemMessageWriter` bound to `ThreadRuntimeService`

## Checklist

- [x] route transcript building through `thread_transcript_builder`
- [x] route metadata writes through `thread_registry_service`
- [x] replace direct audit immutable append helpers with `thread_runtime_service.upsert_system_message()` or equivalent V2 abstraction
- [x] migrate frame audit write path in `node_detail_service.py`
- [x] migrate spec audit write path in `node_detail_service.py`
- [x] migrate rollup package audit write path in `review_service.py`
- [x] add tests proving audit items land in V2 snapshot items
- [x] add code-search or static gate proving production paths no longer call `append_immutable_audit_record(...)`

## Verification

- targeted backend tests for transcript, gating, node-detail, review, lineage, and mixed-mode callers
- code search check for legacy immutable audit helper usage
- manual review of production callsites under `backend/services/`

Verification commands completed successfully:

- `python -m pytest backend/tests/unit/test_frame_generation_service.py backend/tests/unit/test_execution_gating.py backend/tests/unit/test_node_detail_service_audit_v2.py backend/tests/unit/test_thread_lineage_service.py -q`
- `python -m pytest backend/tests/unit/test_review_service.py -q`
- `python -m pytest backend/tests/integration/test_review_api.py -q`
- `python -m pytest backend/tests/unit/test_chat_service.py backend/tests/unit/test_snapshot_view_service.py -q`
- `python -m pytest backend/tests/unit/test_clarify_generation_service.py backend/tests/unit/test_spec_generation_service.py backend/tests/unit/test_split_service.py -q`

## Exit Criteria

- no production metadata consumer writes metadata outside `thread_registry_service`
- no production audit writer remains on V1 immutable append helpers
- critical transcript consumers no longer depend on legacy transcript schema where V2 abstraction exists

Exit criteria status:

- satisfied: `frame_generation_service.py` no longer reads transcript messages directly
- satisfied: production immutable audit writers no longer call `append_immutable_audit_record(...)`
- satisfied: `thread_lineage_service.py` writes registry-first and mirrors legacy session metadata for mixed mode

## Artifacts To Produce

- `artifacts/phase-3/consumer-migration-matrix.md`
- `artifacts/phase-3/audit-writer-cutover-check.md`
- `artifacts/phase-3/code-search-evidence.md`
