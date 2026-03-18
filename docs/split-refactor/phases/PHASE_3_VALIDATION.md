# Phase 3 Validation

Last updated: 2026-03-17

## Commands Run

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_split_contract.py backend/tests/unit/test_split_service.py backend/tests/unit/test_split_service_lineage.py backend/tests/unit/test_split_service_preflight.py backend/tests/integration/test_split_api.py -q
```

## Test Coverage Touched

- `backend/tests/unit/test_split_contract.py`
- `backend/tests/unit/test_split_service.py`
- `backend/tests/unit/test_split_service_lineage.py`
- `backend/tests/unit/test_split_service_preflight.py`
- `backend/tests/integration/test_split_api.py`

## Manual Checks

- Confirmed canonical modes now resolve to `flat_subtasks_v1` at the service layer while legacy bridge modes resolve to distinct legacy output families.
- Confirmed canonical child materialization writes ordered flat subtasks, exact titles, `objective + why_now` descriptions, and stable materialization metadata.
- Confirmed canonical fallback now raises an explicit Phase 4 guard instead of reusing legacy fallback logic.
- Confirmed route-level canonical guard remains active and legacy bridge execution still works through the API.

## Warnings And Residual Risks

- Canonical service execution exists only behind the route guard in this phase; public canonical split is still blocked by design.
- Legacy bridge logic remains live and must be removed later.
- Canonical deterministic fallback is still intentionally absent until Phase 4.

## Validation Outcome

- Passed: `61 passed in 12.24s`
