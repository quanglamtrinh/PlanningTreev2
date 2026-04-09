# Phase 2 - V3 Runtime/Query Native

Status: pending  
Estimate: 6-8 person-days (14%)

## 1. Muc tieu

Xay query/runtime native V3 cho ask/execution/audit, khong phu thuoc snapshot/item V2.

## 2. In-scope

- `ThreadQueryServiceV3`:
  - get snapshot
  - build stream snapshot
  - persist mutation
  - reset thread (ask policy se enforce o route/service layer)
- `ThreadRuntimeServiceV3`:
  - start turn
  - resolve user input
  - begin/complete turn
  - stream agent turn vao item/event V3 canonical
- Loai bo legacy ask mirroring khoi runtime path moi.

## 3. Out-of-scope

- Route cutover production sang V3 services.
- Workflow service cutover (`finish_task`, `execution_audit_workflow`, `review_service`).

## 4. Work breakdown

- [ ] Tao query service moi:
  - `backend/conversation/services/thread_query_service_v3.py`
- [ ] Tao runtime service moi:
  - `backend/conversation/services/thread_runtime_service_v3.py`
- [ ] Dinh nghia event envelope V3 canonical cho persist/publish:
  - snapshot
  - item upsert/patch
  - lifecycle
  - user_input signal
  - thread error
- [ ] Bo sung ledger integration cho pending request V3.
- [ ] Khong goi `sync_legacy_turn_state` tren path V3.
- [ ] Unit tests cho runtime/query V3.

## 5. Deliverables

- Runtime/query service V3 + tests.
- Artifact:
  - `docs/conversion/artifacts/phase-2/runtime-sequence.md`
  - `docs/conversion/artifacts/phase-2/event-contract-v3.md`

## 6. Exit criteria

- Co thể start turn + resolve user input tren runtime/query V3 trong unit/integration isolated test.
- Event stream payload co dinh dang V3 canonical.
- Khong con data dependency bat buoc vao ThreadSnapshotV2.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/unit/test_thread_query_service_v3.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_thread_runtime_service_v3.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_fixture_replay.py`

## 8. Risks va giam thieu

- Risk: mapping raw Codex event -> V3 item semantics drift.
  - Mitigation: replay fixtures + parity fixtures gate.
- Risk: user-input request ledger mismatch.
  - Mitigation: add deterministic tests cho request state transitions.

