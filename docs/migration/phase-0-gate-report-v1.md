# Workflow V2 Phase 0 Gate Report v1

Status: PASS-ready once `python scripts/check_workflow_v2_phase0.py` passes.

Phase 0 freezes the contract boundary before implementation begins. It does not
create Workflow Core V2 modules, add V4 workflow routes, change Breadcrumb
imports, or implement Session Core `thread/inject_items`.

## Current Hybrid Audit

- Session Core V2 is the native runtime/conversation surface under
  `/v4/session/*`.
- `SessionConsoleV2` and Breadcrumb V2 render Session Core V2 transcript,
  composer, model selection, pending request overlays, and interrupt/submit
  commands through `useSessionFacadeV2`.
- Breadcrumb V2 still uses `useWorkflowStateStoreV3`,
  `useWorkflowEventBridgeV3`, `resolveWorkflowProjection`, and V3 workflow
  mutations for execution/audit business decisions.
- Backend `/v4/session/*` is mounted separately and delegates to
  `session_manager_v2`.
- Backend workflow state and execution/audit transitions are still owned by
  `ExecutionAuditWorkflowService` through V3 routes.

## Frozen Phase 0 Decisions

- Workflow business routes use
  `/v4/projects/{projectId}/nodes/{nodeId}/...`.
- `/v4/session/*` remains session-only. Workflow services may call Session Core
  manager/protocol primitives, but session routes must not contain
  PlanningTree workflow business branching.
- Public V4 workflow responses use camelCase, `phase`, and `version`.
- Internal Workflow Core V2 models may use snake_case and `state_version`.
- Legacy V3 compatibility views may continue returning `workflowPhase` and old
  field names until V3 is retired.
- Current V3 `improve-in-execution` maps to V4 `execution/improve`.
- V4 `audit/request-changes` is a separate audit decision action.

## Legacy Phase Mapping

| Legacy V3 `workflowPhase` | Canonical V2 `phase` |
| --- | --- |
| `idle` | `ready_for_execution` |
| `execution_running` | `executing` |
| `execution_decision_pending` | `execution_completed` |
| `audit_running` | `audit_running` |
| `audit_decision_pending` | `review_pending` |
| `done` | `done` |
| `failed` | `blocked` |

## Blockers Before Later Phases

- `thread/inject_items` is required before Thread Binding V2 and context packet
  delivery can be production-ready.
- The existing `.planningtree/workflow_v2` directory name is legacy storage; its
  payload shape is not canonical Workflow Core V2 and must be read through a
  converter.
- Project snapshot and node detail `/v3` reads are outside Phase 0 and may need
  their own migration contract later.

## Verification

Run:

```powershell
python scripts/check_workflow_v2_phase0.py
```

The script verifies the migration docs, key repo path corrections, current
hybrid boundary, session route ownership, and documented prerequisites.
