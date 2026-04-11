# Phase 7 Deletion Log

Date: 2026-04-10

## Backend contract/runtime cleanup

- Removed `lane` from `/v3` route output contract path.
  - `backend/routes/workflow_v3.py` now canonicalizes `threadRole` and strips `lane`.
- Removed backend V3 lane type aliases/utilities.
  - `backend/conversation/domain/types_v3.py`
  - `backend/conversation/projector/thread_event_projector_v3.py`
- Removed transition env-flag parsers and runtime usage.
  - `backend/config/app_config.py`
  - `backend/main.py`
- Removed workflow broker/publisher V2 aliases that were wiring aliases to canonical objects.
  - `backend/main.py`
  - `backend/routes/chat_v2.py`
  - `backend/routes/workflow_v3.py`
- Removed dead adapter file from production codebase.
  - deleted `backend/streaming/conversation_v2_to_v3_event_relay.py`

## Frontend aggressive cleanup

- Removed `lane` from `ThreadSnapshotV3`.
  - `frontend/src/api/types.ts`
- Removed lane fallback reads in active transcript render/parity model.
  - `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
  - `frontend/src/features/conversation/components/v3/messagesV3.parityModel.ts`
- Removed dead V2 state modules.
  - deleted `frontend/src/features/conversation/state/threadByIdStoreV2.ts`
  - deleted `frontend/src/features/conversation/state/threadStoreV2.ts`
  - deleted `frontend/src/features/conversation/state/workflowStateStoreV2.ts`
  - deleted `frontend/src/features/conversation/state/workflowEventBridge.ts`
- Removed unused V2 API client methods/builders that no longer have consumers.
  - `frontend/src/api/client.ts`

## Test and fixture updates

- Updated backend/FE tests from `lane` assertions to canonical `threadRole` behavior on `/v3`.
- Updated parity fixture payloads to canonical `threadRole` naming.
  - `docs/thread-rework/uiux/artifacts/parity-fixtures/execution-audit-v3-parity-fixtures.json`
- Removed deleted FE V2 store test files.
  - deleted `frontend/tests/unit/threadByIdStoreV2.test.ts`
  - deleted `frontend/tests/unit/threadStoreV2.test.ts`
  - deleted `frontend/tests/unit/workflowStateStoreV2.test.ts`
