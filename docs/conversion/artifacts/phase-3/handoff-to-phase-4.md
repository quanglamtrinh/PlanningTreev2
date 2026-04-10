# Phase 3 -> Phase 4 Handoff

Date: 2026-04-10  
From: Conversion Phase 3 (`/v3` Route Native Cutover)  
To: Conversion Phase 4 (Workflow Services Cutover)

## 1. Phase 3 close summary

Phase 3 is closed with `/v3` route dependency cutover completed according to the Phase 3 contract.

- `backend/routes/workflow_v3.py` no longer depends on:
  - `thread_query_service_v2`
  - `thread_runtime_service_v2`
  - `project_v2_snapshot_to_v3`
  - `project_v2_envelope_to_v3`
- By-id route behavior now uses native V3 query/runtime path for snapshot, stream snapshot, resolve, and reset.
- `/v3` stream route consumes only V3 broker events.
- Temporary V2 -> V3 stream compatibility is now handled outside route path via:
  - `backend/streaming/conversation_v2_to_v3_event_relay.py`
- Route contract behavior preserved:
  - canonical `threadRole`
  - temporary `lane` behind `PLANNINGTREE_V3_LANE_COMPAT_MODE`
  - `ask_v3_disabled`, `invalid_request`, and `conversation_stream_mismatch` semantics

Artifacts updated in Phase 3:

- `docs/conversion/artifacts/phase-3/route-cutover-diff.md`

Verification evidence:

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_thread_query_service_v3.py backend/tests/unit/test_thread_runtime_service_v3.py backend/tests/unit/test_phase3_workflow_v3_route_cutover_guards.py`
  - result: `38 passed`
- Route grep acceptance gate:
  - no forbidden V2 route dependencies in `backend/routes/workflow_v3.py`

## 2. Locked boundaries for Phase 4

1. Service ownership cutover is the Phase 4 objective:
- move workflow service write paths (`finish-task`, execution follow-up, audit/review workflows) to V3-native core.
- remove remaining V2 query/runtime usage from service layer production paths.

2. Temporary relay is compatibility-only:
- `RelayingConversationEventBrokerV2` exists only to preserve stream parity during transition.
- it must be removed when execution/audit workflow services emit native V3 envelopes directly.

3. Route/public contract stability remains required:
- no public endpoint path changes.
- keep V3 envelope/error semantics and stream-first snapshot/mismatch guards.

## 3. Phase 4 execution focus

- Cut over:
  - `FinishTaskService`
  - `ExecutionAuditWorkflowService`
  - `ReviewService`
  from V2 query/runtime internals to V3-native services.
- Ensure execution/audit write path no longer mutates legacy transcript paths on production flow.
- Preserve behavior parity and workflow event semantics expected by existing integration tests.

## 4. Entry checklist for Phase 4 PRs

1. Keep `/v3` route behavior unchanged while migrating service internals.
2. Do not regress stream parity or workflow mutation guards.
3. Add/maintain tests for execution/audit workflow service behavior on V3 path.
4. Plan relay removal only after service-level V3 event emission is validated.
5. Publish Phase 4 artifacts:
   - `service-call-graph-before-after.md`
   - `behavior-parity-report.md`
