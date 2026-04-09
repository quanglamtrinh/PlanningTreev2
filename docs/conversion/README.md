# Native V3 End-to-End Conversion Playbook

Updated: 2026-04-09
Owner: PTM Core Team

## 1. Muc tieu

Chuyen PTM tu mo hinh "V3 o lop API/UI + V2 o loi" sang **native V3 end-to-end**:

- V3 la hop dong va runtime canonical duy nhat cho ask/execution/audit.
- `/v3` khong con phu thuoc adapter `project_v2_*`.
- Frontend khong con phu thuoc workflow control plane `/v2`.
- Bo duong dan V2/V1 chi con de compatibility co thoi han, sau do cleanup.

## 2. Hien trang (baseline can dong bang)

Nhung diem da xac nhan trong codebase:

- `backend/main.py` van khoi tao `thread_query_service_v2`, `thread_runtime_service_v2`, `execution_audit_workflow_service_v2`.
- `backend/routes/workflow_v3.py` dang:
  - read snapshot V2
  - map `project_v2_snapshot_to_v3`
  - stream event V2 roi map `project_v2_envelope_to_v3`
  - dispatch mutation qua runtime/workflow service V2
- Storage transcript canonical hien tai la `.planningtree/conversation_v2/...`.
- Runtime ask van con co legacy mirroring sang `chat_state_store`.
- Frontend transcript da dung store V3 by-id, nhung workflow state/mutation/event bridge van dung `/v2`.

He qua: hien tai da co V3 contract ben ngoai, nhung loi van V2.

## 3. Nguyen tac migration

1. Contract behavior truoc, implementation sau.
2. Khong doi API behavior user-facing trong luc doi loi.
3. Registry-first thread identity la bat bien.
4. Streaming guard (`conversation_stream_mismatch`) va first-frame snapshot bat buoc giu.
5. Ask/execution/audit deu phai di qua cung V3 runtime model o diem ket thuc.
6. Co phase migration data + rollback ro rang truoc khi hard cutover.

## 4. Scope migration

In-scope:

- Backend domain/query/runtime/storage/route cho V3 native.
- Workflow services (finish-task, execution decision, audit review, rollup) cutover sang V3 core.
- Frontend workflow control plane cutover sang V3 APIs.
- Data migration tu `conversation_v2` sang `conversation_v3`.
- Hard cleanup code V2 adapter path.

Out-of-scope:

- Thay doi UX hay business policy moi khong lien quan conversion.
- Thay doi lon va khac dac ta o split/frame/clarify/spec ngoai pham vi transcript/runtime cutover.

## 5. Phase map + effort estimate

Tong effort baseline: 100% (uoc luong 42-57 person-days, tuy staffing).

| Phase | Ten phase | Effort % | Uoc luong | Team chinh |
|---|---|---:|---:|---|
| 0 | Baseline freeze + contract gate | 8% | 3-4 PD | BE + FE lead |
| 1 | V3 domain/store foundation | 12% | 5-7 PD | BE |
| 2 | V3 runtime/query native | 14% | 6-8 PD | BE |
| 3 | `/v3` route native cutover | 12% | 4-6 PD | BE |
| 4 | Workflow services cutover | 18% | 8-10 PD | BE |
| 5 | Frontend control-plane V3 | 14% | 6-8 PD | FE |
| 6 | Data migration + compatibility bridge | 10% | 4-6 PD | BE |
| 7 | Hard cutover cleanup | 8% | 4-5 PD | BE + FE |
| 8 | Stabilization + closeout | 4% | 2-3 PD | BE + FE + QA |

## 6. Milestone gates

- Gate A (sau Phase 0): behavior matrix frozen, test acceptance matrix locked.
- Gate B (sau Phase 3): `/v3` route stack da native V3 service.
- Gate C (sau Phase 5): frontend workflow control plane da V3, no V2 dependency tren duong chay chinh.
- Gate D (sau Phase 6): migration tool idempotent + backfill rehearsal pass.
- Gate E (sau Phase 8): no production path su dung V2 core.

## 7. Source-of-truth files trong thu muc nay

- `docs/conversion/progress.yaml`: tracker tien do, status phase, blockers.
- `docs/conversion/phase-0-baseline-and-contract.md`
- `docs/conversion/phase-1-v3-domain-store.md`
- `docs/conversion/phase-2-v3-runtime-query.md`
- `docs/conversion/phase-3-v3-route-cutover.md`
- `docs/conversion/phase-4-workflow-services-cutover.md`
- `docs/conversion/phase-5-frontend-control-plane-v3.md`
- `docs/conversion/phase-6-data-migration.md`
- `docs/conversion/phase-7-hard-cutover-cleanup.md`
- `docs/conversion/phase-8-stabilization-closeout.md`

## 8. Dinh nghia done toan chuong trinh

1. `/v3` khong con goi `thread_query_service_v2`, `thread_runtime_service_v2`, `execution_audit_workflow_service_v2`.
2. Khong con adapter mapping V2->V3 trong production stream/snapshot path.
3. Frontend khong con workflow dependency `/v2/projects/...`.
4. `conversation_v3` la transcript store canonical.
5. Legacy V2 path duoc chot chinh sach deprecation ro rang (hoac remove han neu da dat gate).

