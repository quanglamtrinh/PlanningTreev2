# Phase 0 -> Phase 1 Handoff

Date: 2026-04-10  
From: Conversion Phase 0 (Baseline and Contract Freeze)  
To: Conversion Phase 1 (V3 Domain/Store Foundation)

## 1. Phase 0 close summary

Phase 0 is closed with baseline evidence and locked contracts in place.

- Baseline suite re-run passed (`37` tests total across locked suites).
- Required phase-0 artifacts exist:
  - `behavior-matrix.md`
  - `policy-matrix.md`
  - `decision-log.md`
  - `open-questions.md` (resolved)
- Cross-track precedence is documented: conversion tracker is authoritative for native V3 end-to-end work.

## 2. Locked decisions Phase 1 must implement against

1. Naming and contract
- Canonical V3 naming uses `thread_role` with JSON key `threadRole`.
- Naming transition is phased to avoid route-sequencing conflict:
  - Phase 1: canonicalize domain/store to `threadRole` and normalize legacy `lane` on read.
  - Phase 3: make `/v3` native route output threadRole-primary (temporary lane dual-emit allowed only for migration safety).
  - Phase 5: frontend active path stops reading `lane`.
  - Phase 7: remove `lane` emission and lane-based types/tests.

2. Bridge policy contract
- Read order: V3 first -> optional V2 read-through -> persist V3.
- No V2 back-write from the V3 path.
- Bridge modes: `enabled | allowlist | disabled`.
- Disabled missing-snapshot contract: `409` + `conversation_v3_missing` + `error.details = {}`.
- Bridge config is env-only:
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST` (comma-separated project ids)

3. Workflow events ownership
- Canonical owner for `GET /v3/projects/{project_id}/events` is `backend/routes/workflow_v3.py`.

## 3. Phase 1 execution focus

Phase 1 is foundation-only and must not cut routes yet.

- Build `thread_snapshot_store_v3` with canonical path:
  - `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- Wire `Storage` to expose `thread_snapshot_store_v3` while preserving V2 behavior.
- Add deterministic V3 snapshot normalize/default/copy helpers.
- Keep route behavior unchanged in this phase (including current compatibility payload shape).
- Add unit coverage for:
  - default read when file missing
  - write/read roundtrip
  - malformed payload normalization
  - reset behavior
  - legacy `lane` input normalization to canonical `threadRole`

## 4. Entry checklist for Phase 1 PRs

1. Do not modify production route behavior in this phase.
2. Keep compatibility with current projector/replay tests.
3. Keep changes isolated to domain/store foundation and related tests.
4. Document schema choices in `docs/conversion/artifacts/phase-1/storage-schema.md`.
5. Verify phase-1 target suite before phase exit:
   - `backend/tests/unit/test_conversation_v3_stores.py` (new)
   - `backend/tests/unit/test_conversation_v3_projector.py`
   - `backend/tests/unit/test_conversation_v3_parity_fixtures.py`
