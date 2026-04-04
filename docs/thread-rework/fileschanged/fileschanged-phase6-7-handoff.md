# FilesChanged Rework - Phase 6-7 Handoff (Implemented)

Date: 2026-04-04

## Scope locked for this handoff

- Phase 6: observe-only rollout stabilization for execution/audit file-change migration.
- Phase 7: compat hard cleanup with canonical `changes[]` as authoritative behavior.
- Keep migration policy: new turns only, no historical backfill.
- Keep wire compatibility fields (`outputFiles`, `files*`) in this cycle.

## Phase 6 completion (Observe-only rollout + stabilization)

Status: PASS

- No new feature flag or rollout API was introduced.
- Rollout procedure is release-driven with staged checklist:
  - internal
  - canary
  - broad
- Monitoring uses existing signals:
  - file-change render errors and apply errors
  - forced snapshot reload/reconnect counters already present in V3 store telemetry
  - empty file-change cards on new turns via regression and smoke checks
- Rollback policy is release rollback (revert/deploy), not runtime toggles.

## Phase 7 completion (Compat hard cleanup)

Status: PASS

- Frontend file-change semantics hardening:
  - removed command-text inference path that auto-promoted `commandExecution` to file-change
  - file-change card now requires explicit semantic payload:
    - tool item with `toolType = fileChange`, or
    - diff item with semantic file-change markers (`semanticKind=fileChange` / `v2Kind=tool`)
  - command tools with incidental `outputFiles` remain command cards
- Canonical-first behavior hardening:
  - explicit canonical empty arrays are now authoritative and do not fallback to mirror fields
  - patch reducers/projectors use canonical `changes*` as source of truth when present
  - mirror fields stay synchronized from canonical output
- Migration-only compatibility retained:
  - legacy `filesAppend/filesReplace` and `outputFiles*` patch paths remain supported
  - no public API/type removals in this phase

## Test evidence

### Frontend

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit -- tests/unit/MessagesV3.test.tsx tests/unit/applyThreadEventV3.test.ts
```

Result:

- Typecheck PASS
- Unit suite PASS (`34 passed`, `186 tests`)

### Backend

```bash
python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_conversation_v2_projector.py backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py
python -m pytest -q backend/tests/integration/test_phase5_execution_audit_rehearsal.py backend/tests/integration/test_phase6_execution_audit_cutover.py
```

Result:

- Targeted backend unit suite PASS (`27 passed`)
- Strict phase5/phase6 integration suite PASS (`3 passed`)

## Artifacts

- `docs/thread-rework/fileschanged/artifacts/phase-6/cutover-checklist.md`
- `docs/thread-rework/fileschanged/artifacts/phase-6/smoke-results.md`
- `docs/thread-rework/fileschanged/artifacts/phase-6/rollback-notes.md`
- `docs/thread-rework/fileschanged/artifacts/phase-7/cleanup-checklist.md`
- `docs/thread-rework/fileschanged/artifacts/phase-7/closeout-summary.md`

## Notes

- Wire field hard removal (`outputFiles`/`files*`) is deferred to a later cycle after compat window closes.
- Existing unrelated React Router future-flag warnings still appear in frontend tests but are non-blocking for this migration.
