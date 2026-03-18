# Phase 1 Validation

Last updated: 2026-03-17

## Commands Run

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_split_contract.py backend/tests/integration/test_split_api.py -q
```

## Test Coverage Touched

- `backend/tests/unit/test_split_contract.py`
- `backend/tests/integration/test_split_api.py`

## Manual Checks

- Confirmed the route parser accepts canonical new mode names and the temporary legacy bridge modes.
- Confirmed canonical mode rejection happens at the route layer before `split_service.split_node(...)`.
- Confirmed the existing invalid-mode API contract remains `400 invalid_request`.

## Warnings And Residual Risks

- The temporary legacy route bridge remains active by design and must be removed during later cutover cleanup.
- This phase does not change prompt building, validation, service materialization, fallback, or frontend exposure.

## Validation Outcome

- Passed: `24 passed in 7.06s`
