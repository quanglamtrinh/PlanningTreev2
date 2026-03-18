# Phase 7 Validation

Last updated: 2026-03-17

## Validation Commands Run

```powershell
.\\.venv\\Scripts\\python.exe -m pytest backend/tests/unit/test_split_contract.py backend/tests/unit/test_split_service_preflight.py backend/tests/unit/test_split_service_lineage.py backend/tests/unit/test_concurrency.py backend/tests/unit/test_thread_service.py backend/tests/unit/test_schema_migration.py -q
.\\.venv\\Scripts\\python.exe -m pytest backend/tests/unit/test_split_service.py backend/tests/unit/test_conversation_gateway.py backend/tests/integration/test_split_api.py backend/tests/integration/test_conversation_gateway_api.py -q
Push-Location frontend
npm.cmd exec vitest run tests/unit/project-store.test.ts tests/unit/normalizeSplitPayload.test.ts tests/unit/ConversationSurface.test.tsx
Pop-Location
npm.cmd --prefix frontend run typecheck
rg -n "ReadableSplitMode|LegacySplitMode|walking_skeleton|legacy_epic_phase|legacy_flat_slice|build_legacy_planning_base_instructions|build_legacy_split_user_message|validate_legacy_split_payload|legacy_split_payload_issues|build_legacy_hidden_retry_feedback|payload\\.epics|kind === 'epics'|kind: 'epics'" frontend/src backend/services backend/routes backend/ai backend/storage backend/split_contract.py --glob '!**/.pytest_tmp/**' --glob '!**/pytest_tmp_dir/**'
```

## Validation Coverage

- Canonical-only split contract and service execution remain green after removing the legacy runtime bridge.
- Planning-thread bootstrap and planning-thread fork tests confirm canonical-only base instructions.
- Snapshot migration and runtime read-boundary tests confirm legacy `planning_mode` is normalized away instead of surfacing into runtime state.
- Canonical split payloads still render structured cards, while legacy historical payloads render the stable unsupported notice.
- Targeted runtime search confirms legacy split runtime helpers and transitional mode aliases are no longer present in primary-path runtime code.

## Failures, Warnings, Or Residual Risks

- Historical docs and narrowly scoped migration tests may still mention legacy labels; those are acceptable only outside primary-path runtime code.
- Phase 7 intentionally drops legacy history/replay readability as a supported product guarantee.
- Frontend Vitest still emits pre-existing React warnings about missing keys in `ToolCallBlock` and a few `act(...)` warnings in execution-surface rendering tests; they do not fail the suite and were not introduced by the Phase 7 cutover.

## Final Validation Outcome

- Phase 7 cutover validated with backend pytest coverage, frontend Vitest coverage, frontend typecheck, and a clean runtime-search result for primary-path code.
