# No V1 Audit Writers Check

Phase 5 keeps the Phase 3 audit-writer invariant intact.

## Static Gate

Verification command:

- `python -m pytest backend/tests/unit/test_phase3_no_legacy_audit_writer_callsites.py -q`

Expected result:

- only the helper definition remains at `backend/services/execution_gating.py`
- no production callsite invokes `append_immutable_audit_record(...)`

## Runtime Gate

Phase 5 rehearsal-specific runtime checks now verify:

- execution rehearsal does not publish legacy execution transcript events
- review-rollup rehearsal does not publish legacy audit transcript events
- accepted rollup package writes still go through the V2 system-message writer
- frame and spec audit markers remain on V2 system-message paths

## Evidence

- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/integration/test_phase5_execution_audit_rehearsal.py`
