# FilesChanged Phase 4-5 Parity Report

Date: 2026-04-04

Status: green on scoped Phase 4-5 matrix.

## 1. Execution parity (Phase 4)

Validated:

- strict integration assertions now require canonical `changes[]` plus mirrored `outputFiles[]`
- canonical `changesReplace` remains authoritative (including explicit empty replace)
- hydration path matching covers same-basename files in different directories
- fixture-driven projector parity covers canonical/fallback edge cases

Backend verification:

- `python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py -q`
  - result: `14 passed`
- `python -m pytest backend/tests/integration/test_phase5_execution_audit_rehearsal.py backend/tests/integration/test_phase6_execution_audit_cutover.py -q`
  - result: `3 passed`

## 2. Audit parity (Phase 5)

Validated:

- audit `diff` items with `semanticKind=fileChange` render through shared file-change renderer
- legacy `files.patchText` fallback still renders line-level content in audit lane
- non-fileChange semantic diff rows remain on generic diff card path
- file-change stats are no longer synthesized as `+0/-0` for path-only metadata
- render regression guard added for:
  - `Maximum update depth exceeded`
  - malformed SVG path parse (`<path> attribute d: Expected number`)

Frontend verification:

- `node frontend/node_modules/vitest/vitest.mjs run tests/unit/MessagesV3.test.tsx tests/unit/applyThreadEventV3.test.ts tests/unit/messagesV3.parity.golden.test.ts --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true`
  - result: `21 passed`

## 3. Notes

- These checks target execution/audit lanes only (ask lane untouched).
- Legacy compatibility mirror (`outputFiles`) remains intentionally in place for later cleanup phase.
- Integration rehearsal tests now poll snapshot store directly because `/v2/.../threads/{role}` rejects `execution/audit` roles in current runtime.
