# Phase 3 Route Cutover Diff

Date: 2026-04-10
Owner: PTM Core Team

## Summary

This phase completed native V3 route cutover for `/v3` by-id APIs while intentionally keeping execution mutation orchestration on `execution_audit_workflow_service_v2` until Phase 4.

## Dependency Matrix (Before -> After)

- Snapshot by-id (`GET /v3/projects/{project_id}/threads/by-id/{thread_id}`):
  - before: `thread_query_service_v2` + `project_v2_snapshot_to_v3`
  - after: `thread_query_service_v3` (native)
- Stream by-id (`GET /v3/projects/{project_id}/threads/by-id/{thread_id}/events`):
  - before: `conversation_event_broker_v2` + `project_v2_envelope_to_v3`
  - after: `conversation_event_broker_v3` only, with V2->V3 relay outside route
- Resolve user input by-id (`POST .../requests/{request_id}/resolve`):
  - before: `thread_runtime_service_v2`
  - after: `thread_runtime_service_v3`
- Start turn by-id (`POST .../turns`):
  - before: ask -> `thread_runtime_service_v2`, execution -> workflow service v2
  - after: ask -> `thread_runtime_service_v3`, execution -> workflow service v2
- Plan actions by-id (`POST .../plan-actions`):
  - before: readiness read from `thread_query_service_v2` + projector, dispatch workflow v2
  - after: readiness read from `thread_query_service_v3`, dispatch workflow v2
- Reset by-id (`POST .../reset` ask-only):
  - before: `thread_query_service_v2`
  - after: `thread_query_service_v3`
- Execution mutation orchestration (temporary):
  - before: `execution_audit_workflow_service_v2`
  - after: unchanged intentionally for Phase 3, handoff to Phase 4

## Behavior/Contract Notes

- No endpoint path changes.
- Error envelope remains unchanged (`ok: false`, typed `error.code`, `error.details = {}`).
- Ask role resolution is registry-first; legacy ask-session seeding runs only when bridge policy allows fallback.
- Canonical role field remains `threadRole`.
- Temporary `lane` emission is controlled by `PLANNINGTREE_V3_LANE_COMPAT_MODE`:
  - `enabled` (default): emit `lane`
  - `disabled`: omit `lane`

## Relay Rationale (Temporary)

- Added `RelayingConversationEventBrokerV2` in `backend/streaming/conversation_v2_to_v3_event_relay.py`.
- V2 runtime publishers continue emitting to `conversation_event_broker_v2`.
- Relay maps V2 envelopes to V3 envelopes and republishes to `conversation_event_broker_v3`.
- `/v3` route stream path consumes only V3 broker events and no longer imports/uses route-level V2 projectors.
- Relay is Phase-3 temporary compatibility and must be removed in Phase 4 after execution/audit services emit native V3 events directly.
