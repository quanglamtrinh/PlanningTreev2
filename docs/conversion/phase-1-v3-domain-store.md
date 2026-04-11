# Phase 1 - V3 Domain/Store Foundation

Status: completed  
Estimate: 5-7 person-days (12%)

## 1. Goal

Build native V3 data foundations:

- Add dedicated V3 transcript storage (`conversation_v3`).
- Make V3 snapshot normalization and persistence deterministic.
- Keep this phase focused on foundation only (before route cutover).

## 2. In scope

- V3 thread snapshot store.
- Snapshot default builder and normalizer for V3.
- Read/write/exists/reset behavior for V3 store.
- Unit tests for storage and normalization.

## 3. Out of scope

- `/v3` route migration to V3 services.
- Runtime streaming/mutation behavior.
- Active `/v3` payload lane-removal enforcement (handled in Phase 3/5/7 sequence).

## 4. Work breakdown

- [x] Add new store module:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`
  - Canonical path: `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- [x] Wire into `Storage`:
  - expose `thread_snapshot_store_v3`
  - preserve current V2 path behavior
- [x] Lock naming schema:
  - canonical V3 domain/storage naming uses `thread_role` (JSON key `threadRole`)
  - legacy persisted payloads with `lane` are read-normalized to `threadRole` during load
  - route/output contract tightening (`no lane`) is deferred to Phase 3/5/7 rollout gates
- [x] Add V3 snapshot helpers:
  - default builder
  - normalize function (field hardening)
  - copy/version helpers as needed
- [x] Add unit tests:
  - read default when file is missing
  - write/read roundtrip
  - malformed payload normalization
  - reset behavior
  - verify legacy `lane` payloads normalize to canonical `threadRole`

## 5. Deliverables

- `thread_snapshot_store_v3.py` plus tests.
- `Storage` wiring for V3 store.
- Artifact:
  - `docs/conversion/artifacts/phase-1/storage-schema.md`

## 6. Exit criteria

- V3 store is wired and all related tests pass.
- Existing route behavior is unchanged.
- No required coupling to V2 projector internals.

## 7. Verification

- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_stores.py` (new)
- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py`
- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py`
- [x] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` (route behavior unchanged check)

## 8. Risks and mitigations

- Risk: V3 schema misses fields needed by later workflow phases.
  - Mitigation: freeze schema delta doc before merge.
- Risk: duplicated normalization logic between V2 and V3.
  - Mitigation: extract shared primitive normalization helpers.
