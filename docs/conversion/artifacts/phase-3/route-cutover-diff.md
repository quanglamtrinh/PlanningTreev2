# Phase 3 Route Cutover Diff

Date: 2026-04-10
Owner: PTM Core Team

## Summary

This phase cut over `/v3` route internals to native V3 on ask-thread paths while intentionally keeping execution mutation ownership on `execution_audit_workflow_service_v2`.

## Dependency Matrix (Before -> After)

- Ask snapshot by-id:
  - before: `thread_query_service_v2` + `project_v2_snapshot_to_v3`
  - after: `thread_query_service_v3` (native)
- Ask stream by-id:
  - before: `conversation_event_broker_v2` + `project_v2_envelope_to_v3`
  - after: `conversation_event_broker_v3` (native pass-through)
- Ask start/resolve/reset by-id:
  - before: `thread_runtime_service_v2` / `thread_query_service_v2`
  - after: `thread_runtime_service_v3` / `thread_query_service_v3`
- Execution/audit stream by-id:
  - before: v2 stream + v2->v3 projector
  - after: unchanged intentionally for Phase 3 (hybrid boundary)
- Execution mutation by-id (`/turns` execution branch, `/plan-actions`):
  - before: `execution_audit_workflow_service_v2`
  - after: unchanged intentionally for Phase 3 (handoff to Phase 4)

## Behavior/Contract Notes

- No endpoint path changes.
- Error envelope remains unchanged (`ok: false`, typed `error.code`, `error.details = {}`).
- Ask role resolution remains registry-first; legacy ask-session seeding now runs only when bridge policy allows fallback.
- Canonical role field is emitted as `threadRole`.
- Temporary `lane` emission is controlled by `PLANNINGTREE_V3_LANE_COMPAT_MODE`:
  - `enabled` (default): emit `lane`
  - `disabled`: omit `lane`

## Temporary Compatibility Notes For Phase 4

- Hybrid stream strategy is deliberate in Phase 3.
- Execution/audit stream continues to depend on v2 event source + projector until workflow services are migrated in Phase 4.
- Remove remaining route-level v2 projection path only after execution/audit write path moves to V3-native services.
