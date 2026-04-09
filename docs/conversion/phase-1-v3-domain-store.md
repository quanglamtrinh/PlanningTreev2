# Phase 1 - V3 Domain/Store Foundation

Status: pending  
Estimate: 5-7 person-days (12%)

## 1. Muc tieu

Tao nen tang du lieu native V3:

- Co transcript store V3 rieng (`conversation_v3`).
- Normalize + persist snapshot V3 mot cach deterministic.
- Chua dong toi route cutover, chi dung cho foundation.

## 2. In-scope

- Thread snapshot V3 store.
- Normalizer/default builder cho snapshot V3.
- Co che read/write/exists/reset cho V3 store.
- Unit test cho store + normalization.

## 3. Out-of-scope

- Route `/v3` chuyen sang V3 service.
- Runtime agent streaming va mutation logic.

## 4. Work breakdown

- [ ] Tao module store moi:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`
  - Path de nghi: `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- [ ] Bo sung wiring trong `Storage`:
  - expose `thread_snapshot_store_v3`
  - khong pha vo path V2 hien tai
- [ ] Bo sung domain helper cho V3 snapshot:
  - default builder
  - normalize function (field-level hardening)
  - copy/version helper neu can
- [ ] Viet unit tests:
  - read default khi file chua ton tai
  - write/read roundtrip
  - normalize payload xau
  - reset behavior

## 5. Deliverables

- `thread_snapshot_store_v3.py` + tests.
- `Storage` wiring cho V3 store.
- Artifact note:
  - `docs/conversion/artifacts/phase-1/storage-schema.md`

## 6. Exit criteria

- Co V3 store duoc wiring va co test pass.
- Khong anh huong behavior route hien tai.
- Khong co coupling bat buoc voi projector V2.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_stores.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py`
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py`

## 8. Risks va giam thieu

- Risk: schema V3 thieu field can cho workflow phase sau.
  - Mitigation: freeze schema delta doc truoc khi merge.
- Risk: duplicate logic normalize giua V2/V3.
  - Mitigation: tach helper chung cho primitive field normalization.

