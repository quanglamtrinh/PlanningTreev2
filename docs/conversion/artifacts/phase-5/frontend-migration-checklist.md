# Phase 5 Frontend Migration Checklist

Date: 2026-04-10  
Owner: FE Conversion Track

## Scope Lock

- [x] Active `/chat-v2` workflow control-plane switched to V3 endpoints.
- [x] Active workflow state/actions store wiring switched from V2 store to V3 store.
- [x] Active workflow event bridge switched from `/v2/projects/{id}/events` to `/v3/projects/{id}/events`.
- [x] Active-path `MessagesV3` and parity model decisions switched to canonical `threadRole`.
- [x] `ThreadSnapshotV3` FE type made canonical on `threadRole`; `lane` retained optional as compatibility field.
- [x] V2 workflow API/store/bridge kept only for compatibility, not active-path wiring.

## Code Targets Completed

- API client:
  - Added V3 workflow builders/functions:
    - `buildWorkflowStatePathV3`
    - `buildWorkflowActionPathV3`
    - `buildProjectEventsUrlV3`
    - `getWorkflowStateV3`
    - `finishTaskWorkflowV3`
    - `markDoneFromExecutionV3`
    - `reviewInAuditV3`
    - `markDoneFromAuditV3`
    - `improveInExecutionV3`
- New V3 modules:
  - `frontend/src/features/conversation/state/workflowStateStoreV3.ts`
  - `frontend/src/features/conversation/state/workflowEventBridgeV3.ts`
- Active-path rewiring:
  - `BreadcrumbChatViewV2` now uses `useWorkflowStateStoreV3` + `useWorkflowEventBridgeV3`.
  - `NodeDocumentEditor` finish-task flow now uses `useWorkflowStateStoreV3`.
- Naming migration:
  - `frontend/src/api/types.ts`: `ThreadSnapshotV3.threadRole` canonical, `lane?: ...` deprecated compat.
  - `MessagesV3` and `messagesV3.parityModel` gate by `threadRole` with compat fallback from legacy `lane`.

## Verification Evidence

1. Typecheck

- Command:
  - `npm run typecheck --prefix frontend`
- Result:
  - `tsc -b` passed.

2. Unit Tests

- Command:
  - `npm run test:unit --prefix frontend`
- Result:
  - `38 passed (38)` test files
  - `218 passed (218)` tests

3. Active-path V2 workflow guard checks

- Command:
  - `rg "workflowStateStoreV2|workflowEventBridge\.ts|buildProjectEventsUrlV2|getWorkflowStateV2|finishTaskWorkflowV2|markDoneFromExecutionV2|reviewInAuditV2|markDoneFromAuditV2|improveInExecutionV2" frontend/src/features/conversation/BreadcrumbChatViewV2.tsx frontend/src/features/node/NodeDocumentEditor.tsx frontend/src/features/conversation/state/workflowEventBridgeV3.ts frontend/src/features/conversation/state/workflowStateStoreV3.ts -n`
- Result:
  - no matches

- Command:
  - `rg "/v2/projects/.*/workflow|/v2/projects/.*/events" frontend/src/features/conversation/BreadcrumbChatViewV2.tsx frontend/src/features/node/NodeDocumentEditor.tsx frontend/src/features/conversation/state/workflowEventBridgeV3.ts frontend/src/features/conversation/state/workflowStateStoreV3.ts -n`
- Result:
  - no matches

## Test Additions/Updates (Phase 5)

- Added:
  - `frontend/tests/unit/workflowStateStoreV3.test.ts`
  - `frontend/tests/unit/phase5.active-path-v3.guards.test.ts`
- Updated:
  - `frontend/tests/unit/workflowEventBridge.test.tsx` (now validates V3 bridge wiring)
  - `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
  - `frontend/tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx`
  - `frontend/tests/unit/NodeDetailCard.test.tsx`
  - `frontend/tests/unit/MessagesV3.test.tsx`
  - `frontend/tests/unit/messagesV3.utils.test.ts`
  - `frontend/tests/unit/applyThreadEventV3.test.ts`
  - `frontend/tests/unit/threadByIdStoreV3.test.ts`
