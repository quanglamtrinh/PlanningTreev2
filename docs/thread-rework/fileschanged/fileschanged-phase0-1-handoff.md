# FilesChanged Rework - Phase 0-1 Handoff (Implemented)

Status: completed (Phase 0-1 scope delivered).

Date: 2026-04-03.

Owner scope: freeze contract + backend bridge for execution `fileChange` migration to CodexMonitor-style canonical `changes[]`.

## 1. Scope closed in this handoff

Delivered:

- Phase 0 contract freeze and acceptance matrix implementation
- Phase 1 backend/V3/frontend-state bridge for canonical `changes[]` with compatibility mirrors
- unit/integration-sanity coverage for the locked rules

Explicitly not done in Phase 0-1:

- no historical backfill
- no ask-lane migration
- no renderer cutover in `MessagesV3`/file-change UI (Phase 2-3)

## 2. Contract decisions now locked

Canonical file-change model:

- `changes[]` entries with:
  - `path: string`
  - `kind: 'add' | 'modify' | 'delete'`
  - `diff: string | null`
  - `summary: string | null`

Lifecycle mapping:

- `item/fileChange/outputDelta.params.files` -> preview append (`changesAppend`, `diff=null` when missing)
- `item/completed.item.changes|files` -> authoritative replace (`changesReplace`)
- replace applies when key exists, including explicit empty array
- if completed payload omits both `changes` and `files`, projector keeps preview

Precedence and identity:

- completed payload wins over preview delta
- missing `callId` fallback identity remains `item.id` (required and preserved)

Migration policy:

- apply to new execution turns only
- no rewrite/backfill for historical snapshots
- legacy payloads remain readable via adapters and mirror fields

## 3. Implementation summary

### 3.1 Backend V2 contract/projector bridge

- Added canonical tool-change types and patch ops:
  - `ToolChange`
  - `ToolItem.changes`
  - `ToolPatch.changesAppend/changesReplace`
- Normalization now preserves `kind`/`diff` from upstream `changes/files`.
- Projector patch logic now treats `changes[]` as canonical for `fileChange` and emits synchronized `outputFiles` mirror.
- `item/completed` for `fileChange` now handles explicit empty replace correctly.

### 3.2 V3 projection bridge

- Added V3 canonical diff model:
  - `DiffChangeV3`
  - `DiffItemV3.changes`
  - `DiffPatchV3.changesAppend/changesReplace`
- V2->V3 conversion for `toolType=fileChange` now carries `changes` canonical and generates `files` mirror from it.
- V3 patch application keeps `changes` and `files` synchronized in one mutation path.
- V3 patch mapping from V2 now supports both canonical (`changes*`) and compat (`outputFiles*` -> `files*`) inputs.

### 3.3 Frontend contract/reducer bridge

- Added frontend API types for canonical/mirror transition:
  - `ToolChange`
  - `DiffChangeV3`
  - `changes` on `DiffItemV3`
  - `changesAppend/changesReplace` on `DiffPatchV3`
- `applyThreadEventV3` reducer now accepts `changesAppend/changesReplace` and keeps `changes` <-> `files` synchronized.
- Compat path `filesAppend/filesReplace` still works for legacy events.

## 4. Files changed in Phase 0-1

Backend:

- `backend/conversation/domain/types.py`
- `backend/conversation/projector/thread_event_projector.py`
- `backend/conversation/domain/types_v3.py`
- `backend/conversation/projector/thread_event_projector_v3.py`
- `backend/tests/unit/test_conversation_v2_projector.py`
- `backend/tests/unit/test_conversation_v3_projector.py`

Frontend:

- `frontend/src/api/types.ts`
- `frontend/src/features/conversation/state/applyThreadEventV3.ts`
- `frontend/tests/unit/applyThreadEventV3.test.ts`

## 5. Acceptance matrix (Phase 0-1)

- Canonical `changes[]` available for new execution-turn fileChange items: done
- Completed payload replace is authoritative (including explicit empty array): done
- Missing completed `changes/files` keeps preview: done
- Missing `callId` fallback identity path preserved: done
- V3 patch supports canonical + mirror ops without drift: done
- Frontend reducer accepts `changesAppend/changesReplace` without regressing `files*`: done

## 6. Verification evidence

Backend tests:

- `python -m pytest backend/tests/unit/test_conversation_v2_projector.py backend/tests/unit/test_conversation_v2_fixture_replay.py backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_finish_task_service.py -q`
  - result: `39 passed`
- `python -m pytest backend/tests/unit/test_execution_audit_workflow_service.py -q`
  - result: `2 passed`

Frontend tests:

- `npm --prefix frontend run test:unit -- tests/unit/applyThreadEventV3.test.ts tests/unit/threadByIdStoreV3.test.ts`
  - runner executed full unit suite in this workspace invocation
  - result: `177 passed`
- `npm --prefix frontend run typecheck`
  - result: pass

## 7. Known follow-ups for Phase 2-3

- Switch execution file-change rendering to use canonical `changes[]` as primary source in UI components.
- Keep `files[]` as temporary fallback only during migration window.
- Remove temporary renderer/debug fallback paths after cutover stabilizes.

## 8. Handoff readiness

Phase 0-1 is ready to hand over to Phase 2-3 without reopening contract decisions.
