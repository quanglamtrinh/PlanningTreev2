# Phase 0 - Baseline And Contract Freeze

Status: in_progress  
Estimate: 3-4 person-days (8%)

## 1. Muc tieu

Dong bang "behavior contract" truoc khi doi loi implementation:

- Khong de drift behavior khi thay V2 core bang V3 core.
- Co acceptance gate ro rang cho ask/execution/audit.
- Giai quyet xung dot tai lieu cu trong cac track lien quan.

## 2. In-scope

- Freeze behavior matrix tu test hien co.
- Freeze API policy matrix (/v1, /v2, /v3) trong giai doan conversion.
- Freeze stream contract va error contract.
- Tao artifact de phase sau dung chung.

## 3. Out-of-scope

- Chinh sua implementation runtime/store.
- Remove route hay service legacy.

## 4. Work breakdown

- [ ] Lap baseline matrix tu cac test:
  - `backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - `backend/tests/integration/test_phase6_execution_audit_cutover.py`
  - `backend/tests/unit/test_conversation_v3_projector.py`
  - `backend/tests/unit/test_ask_v3_rollout_phase6_7.py`
- [ ] Dong bang matrix policy route:
  - `/v1 chat ask` -> invalid_request (migration message)
  - `/v2 thread roles ask/execution/audit` -> invalid_request (use /v3 by-id)
  - `/v3 by-id reset` -> ask only
- [ ] Dong bang matrix stream:
  - first frame la `thread.snapshot.v3`
  - incremental item event contract
  - reconnect guard `conversation_stream_mismatch`
- [ ] Dong bang matrix user-input:
  - resolve -> `answer_submitted`
  - UI signal activeUserInputRequests phai cap nhat dung status
- [ ] Chot "legacy docs conflict note" cho track conversion:
  - phase status trong `docs/handoff/conversation-streaming-v2/progress.yaml`
  - handoff ask v3 phase6-7 da PASS

## 5. Deliverables

- `docs/conversion/artifacts/phase-0/behavior-matrix.md`
- `docs/conversion/artifacts/phase-0/policy-matrix.md`
- `docs/conversion/artifacts/phase-0/open-questions.md` (neu con)

## 6. Exit criteria

- Behavior matrix da du cho ask/execution/audit.
- Team dong y lock cac rule trong `progress.yaml`.
- Khong con ambiguity o:
  - stream open sequence
  - by-id role resolution
  - reset policy
  - user-input resolve semantics

## 7. Verification

- [ ] Chay bo test baseline da lock:
  - `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
  - `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py`
  - `python -m pytest -q backend/tests/unit/test_ask_v3_rollout_phase6_7.py`

## 8. Risks va giam thieu

- Risk: matrix khong cover edge case.
  - Mitigation: them "contract gap list" va escalate truoc Phase 1.
- Risk: conflict voi track docs cu.
  - Mitigation: tao note "conversion track precedence" trong artifact.

