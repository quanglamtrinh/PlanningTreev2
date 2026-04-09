# Phase 3 - `/v3` Route Native Cutover

Status: pending  
Estimate: 4-6 person-days (12%)

## 1. Muc tieu

Chuyen route `/v3` sang goi thang service V3 native, xoa phu thuoc adapter V2 trong route path.

## 2. In-scope

- Refactor `backend/routes/workflow_v3.py`:
  - snapshot by-id
  - events by-id
  - start turn by-id
  - resolve user input by-id
  - plan actions by-id
  - reset by-id policy
- Wring app state tu `*_v2` sang service V3 moi trong route path.
- Giu nguyen behavior contract da freeze o phase 0.

## 3. Out-of-scope

- Refactor workflow business services lon.
- Frontend migration.

## 4. Work breakdown

- [ ] Doi dependency route:
  - `thread_query_service_v3`
  - `thread_runtime_service_v3`
  - (tam thoi) workflow service co the con ten `_v2` neu chua phase 4
- [ ] Xoa adapter route-level:
  - bo `project_v2_snapshot_to_v3`
  - bo `project_v2_envelope_to_v3` tren stream path route
- [ ] Giu logic role resolution by-id:
  - execution/audit theo workflow state
  - ask theo registry (co fallback seed tu legacy session chi neu can trong bridge)
- [ ] Giu error semantics:
  - `invalid_request` for mismatch/policy
  - `ask_v3_disabled` gate contract neu gate con ton tai
  - `conversation_stream_mismatch` guard

## 5. Deliverables

- Route `/v3` native service wiring.
- Integration tests update/pass.
- Artifact:
  - `docs/conversion/artifacts/phase-3/route-cutover-diff.md`

## 6. Exit criteria

- `/v3` route khong con read/publish qua query/runtime V2.
- `test_chat_v3_api_execution_audit.py` pass full.
- Stream first-frame + reconnect guard pass.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
- [ ] `python -m pytest -q backend/tests/unit/test_ask_v3_rollout_phase6_7.py`

## 8. Risks va giam thieu

- Risk: drift event ordering tren SSE.
  - Mitigation: freeze explicit event order assertions trong integration test.
- Risk: role resolution by-id regression.
  - Mitigation: add dedicated tests mismatch + registry-seed cases.

