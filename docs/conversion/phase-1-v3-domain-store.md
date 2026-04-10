# Phase 1 - V3 Domain/Store Foundation

Status: pending  
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

## 4. Work breakdown

- [ ] Add new store module:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`
  - Canonical path: `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- [ ] Wire into `Storage`:
  - expose `thread_snapshot_store_v3`
  - preserve current V2 path behavior
- [ ] Lock naming schema:
  - public snapshot/event fields use canonical `thread_role` (JSON key `threadRole`)
  - do not emit `lane` in active V3 snapshot/event payloads
  - legacy persisted payloads with `lane` are read-normalized to `threadRole` during load
- [ ] Add V3 snapshot helpers:
  - default builder
  - normalize function (field hardening)
  - copy/version helpers as needed
- [ ] Add unit tests:
  - read default when file is missing
  - write/read roundtrip
  - malformed payload normalization
  - reset behavior
  - verify output payload does not contain legacy `lane`

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

- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_stores.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py`
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py`

## 8. Risks and mitigations

- Risk: V3 schema misses fields needed by later workflow phases.
  - Mitigation: freeze schema delta doc before merge.
- Risk: duplicated normalization logic between V2 and V3.
  - Mitigation: extract shared primitive normalization helpers.
