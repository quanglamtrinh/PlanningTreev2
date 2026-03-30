# Phase 5: Isolated Execution and Audit Rehearsal

Status: completed.

## Goal

Rehearse the execution plus audit bundle end to end on isolated workspaces before the first production cutover.

Phase 5 is successful only if the existing `/v1` execution and review entrypoints can drive canonical V2 execution and audit threads behind a server-side rehearsal flag, while `/chat-v2` remains the observation surface and no rehearsal turn can run against a workspace outside the configured sandbox root.

## Rollout Shape

- backend gate: `PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL=1`
- backend sandbox root: `PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT=<absolute path>`
- public routes stay unchanged:
  - `/v1/projects/{project_id}/nodes/{node_id}/finish-task`
  - `/v1/projects/{project_id}/nodes/{node_id}/accept-local-review`
  - existing review-rollup entrypoints
- hidden `/chat-v2` remains the only supported rehearsal conversation UI surface
- legacy `/chat` behavior during rehearsal is intentionally out of scope

## Landed Summary

The following Phase 5 slices are landed and treated as complete for rollout purposes:

- config helpers for rehearsal enablement and rehearsal workspace root
- explicit rehearsal safety `AppError` with fail-fast route behavior
- `main.py` wiring for rehearsal config, `thread_runtime_service_v2`, and `workflow_event_publisher_v2`
- V2 execution rehearsal branch in `FinishTaskService`
- V2 review-rollup rehearsal branch in `ReviewService`
- raw-event projector path reused for execution and review-rollup turns without `PartAccumulator`
- no legacy execution or rollup transcript events emitted while rehearsal mode is enabled
- `fileChange` preview entries remain incremental, but final lists converge through `outputFilesReplace`
- workflow side-channel events are published during rehearsal so Phase 4 workflow bridge behavior remains valid
- dedicated unit and integration tests for rehearsal gate, V2 snapshots, no-legacy-event behavior, and route-level safety

## Implementation Notes

### Rehearsal safety

- rehearsal mode is off by default
- when rehearsal mode is on, execution and rollup starts are allowed only if the attached project workspace resolves under `PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT`
- unsafe workspaces fail fast with `execution_audit_v2_rehearsal_workspace_unsafe`
- no new routes were introduced for Phase 5

### Execution rehearsal path

- `FinishTaskService.finish_task()` keeps existing validation and execution-state mutation
- when rehearsal mode is enabled, execution conversation branches into `thread_runtime_service_v2.begin_turn(...)` plus raw-event projection
- rehearsal execution does not publish `message_created`, `assistant_delta`, `assistant_tool_call`, `assistant_completed`, or `execution_completed`
- canonical execution conversation lives only in the V2 `execution` thread snapshot
- V1 execution chat session remains only as legacy active-turn metadata mirror and stays empty of assistant transcript content in rehearsal mode

### Audit rehearsal path

- `ReviewService.start_review_rollup()` branches into a V2 runtime path when rehearsal mode is enabled
- rehearsal rollup does not publish `message_created`, `assistant_delta`, or `assistant_completed`
- canonical audit conversation lives only in the V2 `audit` thread snapshot
- accepted rollup package persistence remains on the V2 system-message writer introduced in Phase 3
- `node_detail_service.py` frame/spec writes and `review_service.py` rollup package writes remain on V2 abstractions only

### Intentional Phase 5 boundary

Phase 5 does not rehearse the legacy auto-review assistant transcript path.

Instead, once V2 execution rehearsal completes successfully, the flow advances into the existing local-review state so the manual `accept-local-review -> rollup` path can rehearse audit on canonical V2 threads without reintroducing V1 audit transcript writes. This keeps the rehearsal bundle focused on execution conversation, audit system records, local-review acceptance, and review-rollup conversation.

## File Targets

- `backend/config/app_config.py`
- `backend/errors/app_errors.py`
- `backend/main.py`
- `backend/conversation/services/thread_runtime_service.py`
- `backend/services/finish_task_service.py`
- `backend/services/review_service.py`
- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/unit/test_phase3_no_legacy_audit_writer_callsites.py`
- `backend/tests/integration/test_phase5_execution_audit_rehearsal.py`

## Final Verification

Focused verification completed on 2026-03-28:

- `python -m pytest backend/tests/unit/test_finish_task_service.py backend/tests/unit/test_review_service.py -q`
- `python -m pytest backend/tests/integration/test_phase5_execution_audit_rehearsal.py -q`
- `python -m pytest backend/tests/unit/test_phase3_no_legacy_audit_writer_callsites.py -q`
- `python -m pytest backend/tests/unit/test_system_message_writer.py backend/tests/unit/test_conversation_v2_projector.py -q`

Results:

- unit rehearsal branch coverage passed: `35` tests
- phase 5 integration suite passed: `2` tests
- no-legacy-audit-writer code-search gate passed: `1` test
- projector and system-message regression coverage passed: `8` tests

Covered behaviors:

- rehearsal flag on/off service branching
- sandbox-root rejection before execution start
- canonical V2 execution snapshot updates through raw-event projection
- canonical V2 audit snapshot updates through review-rollup raw-event projection
- `fileChange` preview overwrite by authoritative `outputFilesReplace`
- provisional raw tool-call collapse when typed tool item arrives
- no legacy execution or rollup transcript events on the rehearsal path
- route-level safety rejection for workspaces outside the rehearsal root
- workflow side-channel publisher activity during rehearsal

## Exit Criteria

- rehearsal path rejects workspaces outside the configured sandbox root
- execution conversation can complete on the canonical V2 `execution` thread
- review-rollup conversation can complete on the canonical V2 `audit` thread
- no production-path audit writer remains on legacy immutable append helpers
- no rehearsal execution or rollup path emits legacy transcript events
- `fileChange` final file lists overwrite preview entries correctly

All exit criteria above are satisfied for Phase 5 closeout.

## Phase 6 Handoff

Phase 6 can assume:

- execution and review-rollup rehearsal paths already exist behind a server-side flag
- rehearsal path safety is enforced at route-entry time through an explicit typed error
- `/chat-v2` can observe execution and audit V2 threads without additional frontend transport work
- accepted rollup package system messages and frame/spec audit markers are already V2-only
- `fileChange` final file lists converge through `outputFilesReplace`

Phase 6 still needs to decide the production cutover policy for the old auto-review transcript path, since Phase 5 intentionally advances straight into local-review state instead of replaying the legacy audit assistant transcript.

## Artifacts To Produce

- `artifacts/phase-5/README.md`
- `artifacts/phase-5/rehearsal-runbook.md`
- `artifacts/phase-5/rehearsal-results.md`
- `artifacts/phase-5/no-v1-audit-writers-check.md`
