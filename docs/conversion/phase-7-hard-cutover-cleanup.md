# Phase 7 - Hard Cutover Cleanup

Status: pending  
Estimate: 4-5 person-days (8%)

## 1. Muc tieu

Loai bo duong chay V2 adapter khoi production code path sau khi da on dinh.

## 2. In-scope

- Remove hoac deprecate hard:
  - `thread_query_service_v2` production wiring
  - `thread_runtime_service_v2` production wiring
  - `project_v2_snapshot_to_v3` va `project_v2_envelope_to_v3` trong route path production
  - V2-only dead stores tren frontend
- Rename service/state cho ro "V3 canonical".
- Cap nhat docs architecture chinh.

## 3. Out-of-scope

- Feature moi.
- Experiment rollout moi.

## 4. Work breakdown

- [ ] Clean DI trong `backend/main.py` de service naming khong con `_v2` cho path canonical.
- [ ] Remove code branches compatibility khong con su dung.
- [ ] Code search gate:
  - khong con call V2 core tu `/v3` path
  - khong con FE active path call workflow `/v2`
- [ ] Update tests theo naming moi.
- [ ] Danh dau deprecation strategy cho V2 APIs neu van giu route compatibility.

## 5. Deliverables

- Pull request cleanup lon (co checklists).
- Artifact:
  - `docs/conversion/artifacts/phase-7/deletion-log.md`
  - `docs/conversion/artifacts/phase-7/deprecation-notice.md`

## 6. Exit criteria

- Code search khong con V2 adapter dependency tren production path.
- Test gate pass sau cleanup.
- Architecture docs reflect native V3 reality.

## 7. Verification

- [ ] Full targeted backend suite cho conversation/workflow.
- [ ] Frontend typecheck + unit.
- [ ] Search gate scripts (rg-based) pass.

## 8. Risks va giam thieu

- Risk: xoa code som gay regression edge-case chua thay.
  - Mitigation: chi cleanup sau Phase 6 stabilization proof.
- Risk: hidden transitive import V2.
  - Mitigation: enforce forbidden import check trong CI.

