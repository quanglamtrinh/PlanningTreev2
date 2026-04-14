# Phase 11 to Phase 12 Handoff

Status: Ready for implementation handoff.

Date: 2026-04-14.

Source phase: `phase-11-heavy-compute-off-main-thread` (D05, D06, D07).

Target phase: `phase-12-data-volume-and-heavy-content-ux` (D08, E01, E02, E03).

## 1. Handoff Summary

Phase 11 completed and validated:

- markdown parse scheduling offloaded from eager-all to visibility/deferred policy
- diff heavy parse/stats/line artifacts offloaded to worker with guarded apply
- command streaming tail moved to append-aware incremental updates
- candidate-backed Phase 11 gate evidence passes all P11 gates

## 2. Guarantees for Phase 12

Phase 12 may assume:

1. heavy compute pressure on main thread is reduced and measured through P11 gates.
2. async worker paths are governed by version tokens and deterministic stale-drop.
3. fallback sync behavior remains available and semantically equivalent.
4. rollout controls already exist for safe activation (`off`, `shadow`, `on`).

## 3. Implemented Components

Frontend:

- `frontend/src/features/conversation/components/ConversationMarkdown.tsx`
- `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/src/features/conversation/components/v3/parseArtifactCache.ts`
- `frontend/src/features/conversation/components/v3/commandOutputTail.ts`
- `frontend/src/features/conversation/components/v3/phase11Config.ts`
- `frontend/src/features/conversation/components/v3/phase11DiffWorkerProtocol.ts`
- `frontend/src/features/conversation/components/v3/phase11DiffWorkerRuntime.ts`
- `frontend/src/features/conversation/components/v3/phase11DiffWorker.ts`

Gate scripts:

- `scripts/phase11_heavy_payload_profile.py`
- `scripts/phase11_worker_versioning_tests.py`
- `scripts/phase11_heavy_content_interaction_smoke.py`
- `scripts/phase11_gate_report.py`

## 4. Validation Snapshot

Completed validations:

- frontend typecheck -> pass
- targeted frontend unit tests for V3 + phase11 paths -> pass
- render freeze validation -> pass
- P11 gate report with candidate-backed evidence -> pass

Evidence artifacts:

- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/heavy_payload_profile.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/worker_versioning_tests.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/heavy_content_interaction_smoke.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/phase11-gate-report.json`

## 5. Follow-up Actions for Phase 12

1. build heavy-content visibility policy on top of Phase 11 scheduling/worker controls.
2. avoid reintroducing eager-all parse behavior for very long histories.
3. keep worker stale-drop contract intact when adding volume/collapse UX controls.
4. preserve anchor and ordering invariants while introducing data-volume caps and previews.

## 6. Residual Risks and Notes

1. phase11 evidence currently uses candidate scaffolds; production capture should replace with real-run telemetry artifacts when available.
2. worker offload thresholds may need retuning with real user workloads in Phase 12.
3. heavy-content classification accuracy becomes critical once collapse defaults and preview policies are added.

## 7. Decision and Contract Linkage

This handoff remains governed by:

- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/contracts/c5-frontend-state-contract-v1.md`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/README.md`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/close-phase-v1.md`
