# FilesChanged Rework - Phase 2-3 Handoff (Implemented)

Status: completed (Phase 2-3 scope delivered).

Date: 2026-04-03.

Owner scope: execution diff hydration and frontend renderer cutover (execution lane first, CodexMonitor-style `changes[]`).

## 1. Scope closed in this handoff

Delivered:

- Phase 2 backend hydration now patches canonical `changesReplace` per file (with diff text) and keeps `outputFilesReplace` as compatibility mirror.
- Phase 3 frontend execution renderer now consumes canonical file-change payload first (`changes[]` -> per-file diff render/stat).
- `MessagesV3` diff adapter no longer depends on `patches.join()` as sole source; canonical `changes` is carried through synthetic file-change rows.
- debug render snapshot logging removed from file-change row.
- malformed SVG path in file-change copy icon fixed.

Explicitly not done in Phase 2-3:

- no historical backfill or snapshot rewrite.
- no ask-lane migration.
- no rollout gate / canary rollout (Phase 6).
- no audit-lane adoption (Phase 5 optional).

## 2. Contract and behavior now in effect

Canonical runtime behavior for execution file-change:

- Hydration target is canonical `changes[]` via `changesReplace`.
- `outputFilesReplace` is still emitted as compatibility mirror from canonical changes.
- If item already has structured diff text in `outputText`/`argumentsText`, hydration is skipped.
- If canonical/file payload already has non-empty per-file `change.diff`, hydration is skipped.
- Worktree diff query still tries path-scoped diff first, then falls back to full diff if scoped result is empty.

Frontend execution rendering behavior:

- Primary render source is canonical per-file diff (`item.changes[].diff` when available in adapted tool row).
- Fallback chain remains for compatibility:
  - canonical `changes[].diff`
  - mirrored `outputFiles[].diff/summary`
  - legacy blob parsing from `outputText`/`argumentsText`
- Multi-file expansion renders per-file panel content; no full-blob duplication as default behavior.

## 3. Implementation summary

### 3.1 Backend hydration (Phase 2)

Updated `ExecutionAuditWorkflowService._hydrate_execution_file_change_diff_from_worktree` to:

- extract baseline file list from canonical `item.changes` first, fallback `item.outputFiles`.
- parse unified diff by `diff --git ...` blocks.
- match diff blocks to file paths using normalized path match order:
  - exact
  - suffix/containment
  - basename fallback
- patch tool item with:
  - `changesReplace` (per-file `diff`)
  - `outputFilesReplace` mirror synchronized from canonical changes

### 3.2 Frontend file-change row cutover (Phase 3)

`FileChangeToolRow` now:

- builds canonical row model from `item.changes` + compatibility merge from `item.outputFiles`.
- computes `+/-` stats per row from per-file diff first.
- renders expanded content directly from per-file diff when present.
- uses blob parser only as legacy fallback.
- removes `console.info` render snapshot side-effect.
- fixes malformed SVG path in copy icon to avoid `<path d>` parse warnings.

### 3.3 `MessagesV3` diff adapter cutover

`MessagesV3` now:

- maps `diff` items to synthetic file-change tool rows with canonical `changes`.
- mirrors `outputFiles` from canonical changes with `kind`/`diff` preserved.
- keeps compatibility behavior for cases that still only provide files metadata.

## 4. Files changed in Phase 2-3

Backend:

- `backend/services/execution_audit_workflow_service.py`
- `backend/tests/unit/test_execution_audit_workflow_service.py`

Frontend:

- `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/tests/unit/MessagesV3.test.tsx`

## 5. Acceptance matrix (Phase 2-3)

- [x] attach per-file patch text for new execution turns (canonical `changesReplace`)
- [x] keep no-op behavior when structured diff already exists
- [x] validate path-to-hunk matching and full-diff fallback behavior
- [x] switch execution file-change renderer primary source to canonical file-change entries
- [x] ensure `+/-` counters come from per-file patch content
- [x] keep legacy fallback path for older/path-only turns
- [x] remove debug path that can create render-noise loops
- [x] add frontend unit coverage for canonical single-file + multi-file expand scenarios

## 6. Verification evidence

Backend tests:

- `python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py`
  - result: `4 passed`

Frontend tests:

- `npm --prefix frontend run test:unit -- tests/unit/MessagesV3.test.tsx tests/unit/ConversationFeed.test.tsx`
  - workspace script executes `vitest run tests/unit ...`
  - result in this run: `34 passed`
- `npm --prefix frontend run typecheck`
  - result: pass

## 7. Residual risks and notes

- Path-to-hunk matching remains heuristic for extreme rename/duplicate-basename diff shapes; Phase 4 parity fixtures should keep widening coverage.
- Large per-file diff payloads may still affect render performance; Phase 4 should add stress/fixture checks.
- Manual browser-level verification for console cleanliness (no max update depth / no SVG warning) should be captured in Phase 4 parity artifacts, although code-level fixes are in place here.

## 8. Pickup guidance for Phase 4-5

- Add fixture-driven parity tests for:
  - multi-file same-basename path collisions
  - rename/move edge cases
  - large patch payload rendering performance
- Add explicit regression tests for fallback behavior on legacy turns.
- Keep execution as source of truth before enabling audit-lane adoption.
