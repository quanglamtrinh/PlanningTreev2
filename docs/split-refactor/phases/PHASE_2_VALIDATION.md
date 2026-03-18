# Phase 2 Validation

Last updated: 2026-03-17

## Commands Run

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_split_prompt_builder.py backend/tests/unit/test_legacy_split_prompt_builder.py backend/tests/unit/test_split_contract.py backend/tests/integration/test_split_api.py -q
```

## Test Coverage Touched

- `backend/tests/unit/test_split_prompt_builder.py`
- `backend/tests/unit/test_legacy_split_prompt_builder.py`
- `backend/tests/unit/test_split_contract.py`
- `backend/tests/integration/test_split_api.py`

## Manual Checks

- Confirmed `backend/services/thread_service.py` now imports legacy planning instructions rather than the canonical prompt-builder module.
- Confirmed `backend/services/split_service.py` now imports legacy split helpers so the temporary old-mode runtime stays on the bridge path.
- Confirmed the canonical parser preserves list order, normalizes whitespace, and rejects legacy payload keys instead of aliasing them.
- Confirmed the Phase 1 route guard remains the active execution gate for canonical modes.

## Warnings And Residual Risks

- Canonical prompt/schema support landed before service materialization and fallback migration, so the 4 new modes remain intentionally non-executable.
- The temporary legacy bridge is still active by design and must be removed during later cutover cleanup.
- This phase does not change `SplitService` materialization, deterministic fallback behavior, or frontend exposure.

## Validation Outcome

- Passed: `68 passed in 5.93s`
