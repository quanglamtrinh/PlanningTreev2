# Phase 4 Service Call Graph (Before -> After)

Date: 2026-04-10  
Owner: PTM Core Team

## Summary

Phase 4 moved production execution/audit workflow services to native V3 runtime/query semantics and activated `/v3` workflow control-plane endpoints in `workflow_v3.py`.

## Production Path Diff

### Before (end of Phase 3)

- `/v1/projects/{project_id}/nodes/{node_id}/finish-task`
  - `nodes.py` -> `FinishTaskService`
  - production execution path used V2-oriented runtime/query coupling
- `/v3` by-id routes were V3-native for snapshot/stream/turn/reset, but execution mutation orchestration still delegated to `execution_audit_workflow_service_v2` alias path
- `/v3` workflow control-plane endpoints (`workflow-state`, `workflow/*`, `project events`) were not fully owned/active in `workflow_v3.py`
- Production wiring still used `RelayingConversationEventBrokerV2` to bridge V2 emits into V3 stream path

### After (Phase 4 complete)

- `/v1/projects/{project_id}/nodes/{node_id}/finish-task`
  - `nodes.py` -> `FinishTaskService`
  - runtime/query dependency is V3 (`thread_runtime_service_v3` + `thread_query_service_v3`)
- `/v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `workflow_v3.py` -> canonical `execution_audit_workflow_service`
- `/v3/projects/{project_id}/nodes/{node_id}/workflow/*` actions
  - `workflow_v3.py` -> canonical `execution_audit_workflow_service` mutations
- `/v3/projects/{project_id}/events`
  - `workflow_v3.py` -> canonical workflow broker wiring from app state
- Production conversation stream wiring no longer depends on `RelayingConversationEventBrokerV2`

## Wiring Deltas

- Added config parser in `backend/config/app_config.py`:
  - `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED` (default `true`)
- App state canonicalization:
  - canonical `execution_audit_workflow_service`
  - compatibility alias `execution_audit_workflow_service_v2` -> same instance
- Service constructors hardened for V3 query/runtime access:
  - no production dependency on `runtime_v2._query_service` private internals

## Compatibility Notes

- `/v2` workflow endpoints remain compatibility-only in Phase 4.
- `_v2` aliases remain available for compatibility tests/incremental rollout, but are no longer the primary production service path.
