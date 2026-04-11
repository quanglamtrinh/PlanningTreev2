# Phase 5 -> Phase 6 Handoff

Date: 2026-04-10  
From: Conversion Phase 5 (Frontend Control Plane V3 Cutover)  
To: Conversion Phase 6 (Batch Migration And Bridge Sunset)

## 1. Phase 5 close summary

Phase 5 is closed with active frontend workflow control-plane cut over to V3 endpoints while preserving `/chat-v2` UX parity.

- Active FE workflow modules now use V3 path:
  - `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
    - `useWorkflowStateStoreV3`
    - `useWorkflowEventBridgeV3`
  - `frontend/src/features/node/NodeDocumentEditor.tsx`
    - finish-task mutation via `useWorkflowStateStoreV3`
- API client now has V3 workflow control-plane functions:
  - `getWorkflowStateV3`
  - `finishTaskWorkflowV3`
  - `markDoneFromExecutionV3`
  - `reviewInAuditV3`
  - `markDoneFromAuditV3`
  - `improveInExecutionV3`
  - `buildProjectEventsUrlV3`
- FE naming contract aligned on canonical `threadRole`:
  - `ThreadSnapshotV3.threadRole` is canonical
  - `lane` remains optional deprecated compatibility field
  - active plan-ready gating in `MessagesV3` uses `threadRole` (with temporary compat fallback)
- Phase 5 artifacts published:
  - `docs/conversion/artifacts/phase-5/frontend-migration-checklist.md`
  - `docs/conversion/artifacts/phase-5/frontend-regression-notes.md`

Verification evidence:

- `npm run typecheck --prefix frontend`
  - result: pass
- `npm run test:unit --prefix frontend`
  - result: `38 passed` files, `218 passed` tests

## 2. Locked boundaries for Phase 6

1. Phase 5 frontend cutover is now baseline:
- Do not reintroduce V2 workflow APIs/store/bridge on active `/chat-v2` path.

2. Contract stability remains required:
- Keep existing V3 API envelopes and endpoint contracts unchanged while running migration/sunset work.

3. Naming sequence remains enforced:
- `threadRole` is canonical.
- `lane` cleanup/removal remains Phase 7 hard-cutover scope.

4. Phase 6 scope is backend migration/sunset:
- Focus on data migration tooling, batch rollout, and bridge sunset controls.
- Avoid expanding Phase 6 into FE surface rewiring.

## 3. Phase 6 execution focus

- Implement batch migration tool for `conversation_v2` -> `conversation_v3`.
- Guarantee idempotent reruns and robust dry-run/report outputs.
- Finalize bridge sunset operation path:
  - mode progression `enabled -> allowlist -> disabled`
  - disabled-mode typed error behavior (`conversation_v3_missing`)
- Publish migration runbook + report template artifacts.

## 4. Entry checklist for Phase 6 PRs

1. Add migration command and tests with idempotency assertions.
2. Provide dry-run/report evidence on sample projects before real migration execution.
3. Keep per-node failure isolation and summarized migration stats (converted/skipped/failed).
4. Validate bridge disabled rehearsal behavior and rollback instructions.
5. Publish Phase 6 artifacts:
   - `docs/conversion/artifacts/phase-6/migration-runbook.md`
   - `docs/conversion/artifacts/phase-6/migration-report-template.json`
