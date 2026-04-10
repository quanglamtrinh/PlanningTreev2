# Native V3 End-to-End Conversion Playbook

Updated: 2026-04-10  
Owner: PTM Core Team

## 1. Goal

Move PTM from the current model ("V3 at UI/API, V2 in core engine") to a fully **native V3 end-to-end** architecture:

- V3 is the only canonical contract and runtime model for ask/execution/audit.
- `thread_role` is the canonical naming key across API/domain/storage.
- `lane` terminology is deprecated and must not be emitted by active V3 APIs.
- `/v3` no longer depends on `project_v2_*` adapters.
- Frontend no longer depends on workflow control-plane `/v2` APIs.
- V1/V2 compatibility paths become temporary and are removed after hard cutover.

## 2. Current baseline

Confirmed codebase reality:

- `backend/main.py` still wires `thread_query_service_v2`, `thread_runtime_service_v2`, and `execution_audit_workflow_service_v2`.
- `backend/routes/workflow_v3.py` currently:
  - reads V2 snapshots
  - maps `project_v2_snapshot_to_v3`
  - streams V2 events then maps `project_v2_envelope_to_v3`
  - dispatches mutations into V2 runtime/workflow services
- Canonical transcript storage is currently `.planningtree/conversation_v2/...`.
- Ask runtime still includes legacy mirroring into `chat_state_store`.
- Frontend transcript already uses V3 by-id store, but workflow state/mutation/event bridge still use `/v2`.

Consequence: public-facing contract is V3, but core runtime/storage remains V2.

## 3. Migration principles

1. Freeze behavior contract first, then implementation.
2. Preserve user-facing API behavior during migration.
3. Keep registry-first thread identity invariant.
4. Preserve stream guards (`conversation_stream_mismatch`) and first-frame snapshot semantics.
5. Ensure ask/execution/audit all run on the same V3 core model in final state.
6. Start compatibility read bridge early (Phase 2), not only during late migration.
7. Keep explicit migration and rollback paths before hard cutover.

## 3.1 Locked decisions (2026-04-10)

1. Rename cutover now:
   - Canonical V3 snapshot/event field is `thread_role` (JSON key `threadRole`).
   - Legacy `lane` is read-compat only and must not be emitted by active `/v3` routes.
2. Workflow control-plane active path:
   - Primary frontend path must call only locked `/v3` workflow-state, workflow actions, and project events endpoints.
   - `/v2` workflow endpoints remain temporary compatibility only until cleanup phases.
3. Compatibility bridge policy:
   - Read order is `conversation_v3` first, fallback read-through from V2, then persist V3.
   - No V2 back-write on the new V3 path.
   - Bridge mode is explicit: `enabled | allowlist | disabled`.
   - In `disabled`, missing V3 snapshot must return typed `conversation_v3_missing`.

## 4. Scope

In scope:

- Backend V3-native domain/query/runtime/storage/routes.
- Workflow service cutover (finish-task, execution decisions, audit review, rollup) to V3 core.
- Frontend workflow control-plane cutover to locked V3 contract endpoints.
- Data migration from `conversation_v2` to `conversation_v3`.
- Hard cleanup of V2 adapter paths.

Out of scope:

- New UX/business policy changes unrelated to conversion.
- Broad redesign of split/frame/clarify/spec beyond transcript/runtime conversion needs.

## 5. Phase map and effort estimate

Total effort baseline: 100% (estimated 42-57 person-days, staffing-dependent).

| Phase | Name | Effort % | Estimate | Primary team |
|---|---|---:|---:|---|
| 0 | Baseline freeze + contract gate | 8% | 3-4 PD | BE + FE lead |
| 1 | V3 domain/store foundation | 12% | 5-7 PD | BE |
| 2 | V3 runtime/query native + read bridge | 14% | 6-8 PD | BE |
| 3 | `/v3` route native cutover | 12% | 4-6 PD | BE |
| 4 | Workflow services cutover | 18% | 8-10 PD | BE |
| 5 | Frontend control-plane V3 | 14% | 6-8 PD | FE |
| 6 | Batch migration + bridge sunset | 10% | 4-6 PD | BE |
| 7 | Hard cutover cleanup | 8% | 4-5 PD | BE + FE |
| 8 | Stabilization + closeout | 4% | 2-3 PD | BE + FE + QA |

## 6. Milestone gates

- Gate A (after Phase 0): behavior matrix and acceptance tests are frozen.
- Gate B (after Phase 3): `/v3` route stack is fully on native V3 services.
- Gate C (after Phase 5): frontend workflow control-plane is V3-only in active path.
- Gate D (after Phase 6): batch migration passes and bridge sunset plan is validated.
- Gate E (after Phase 8): no production path depends on V2 core runtime.

## 7. Source-of-truth files

- `docs/conversion/progress.yaml` (status tracker, locked decisions, dependencies)
- `docs/conversion/phase-0-baseline-and-contract.md`
- `docs/conversion/phase-1-v3-domain-store.md`
- `docs/conversion/phase-2-v3-runtime-query.md`
- `docs/conversion/phase-3-v3-route-cutover.md`
- `docs/conversion/phase-4-workflow-services-cutover.md`
- `docs/conversion/phase-5-frontend-control-plane-v3.md`
- `docs/conversion/phase-6-data-migration.md`
- `docs/conversion/phase-7-hard-cutover-cleanup.md`
- `docs/conversion/phase-8-stabilization-closeout.md`
- `docs/conversion/workflow-v3-control-plane-contract.md`

## 8. Program-level definition of done

1. `/v3` no longer calls `thread_query_service_v2`, `thread_runtime_service_v2`, or `execution_audit_workflow_service_v2`.
2. Production stream/snapshot paths no longer use V2-to-V3 adapter mapping.
3. Frontend active workflow path no longer depends on `/v2/projects/...`.
4. `conversation_v3` is canonical transcript storage.
5. Public contract naming is consistently `thread_role` (no `lane` terminology).
6. Legacy V2 deprecation/removal policy is fully documented and enforced.
