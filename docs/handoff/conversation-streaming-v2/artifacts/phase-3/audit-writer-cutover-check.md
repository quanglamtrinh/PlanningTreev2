# Phase 3 Audit Writer Cutover Check

## Goal

Prove that production immutable audit writers no longer persist audit records through the legacy V1 helper.

## Stable Audit Marker Ids

- `audit-record:frame`
- `audit-record:spec`
- `audit-package:rollup`

## Production Writer Outcomes

| Writer path | Old behavior | Phase 3 behavior |
| --- | --- | --- |
| `NodeDetailService.confirm_frame()` | wrote legacy immutable audit message | writes canonical V2 system message item `audit-record:frame` |
| `NodeDetailService.confirm_spec()` | wrote legacy immutable audit message | writes canonical V2 system message item `audit-record:spec` |
| `ReviewService.accept_rollup_review()` | wrote legacy immutable audit message | writes canonical V2 system message item `audit-package:rollup` |

## Verification Coverage

- `backend/tests/unit/test_node_detail_service_audit_v2.py`
  - confirms frame writes `audit-record:frame` into V2 snapshot items
  - confirms spec writes `audit-record:spec` into V2 snapshot items
- `backend/tests/unit/test_review_service.py`
  - confirms rollup acceptance writes `audit-package:rollup` into the parent audit V2 snapshot
- `backend/tests/integration/test_review_api.py`
  - confirms route-level rollup acceptance persists `audit-package:rollup` into parent audit V2 snapshot

## Remaining Legacy Helper State

- `append_immutable_audit_record(...)` remains defined in `backend/services/execution_gating.py`
- it is retained only as a compatibility helper for legacy tests or future cleanup work
- no production callsite under `backend/services/`, `backend/routes/`, or `backend/main.py` invokes it after Phase 3
