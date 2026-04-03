# Execution/Audit Hard Cutover to V3

Date: 2026-04-03

## Scope

- execution thread: V3 only
- audit thread: V3 only
- ask lane: unchanged

## What Changed

### Frontend

- execution/audit routing now always resolves to `chat-v2` surface with `MessagesV3` + `threadByIdStoreV3`.
- runtime gate selection logic for execution/audit V2<->V3 paths was removed.
- legacy gate-dependent navigation from graph/sidebar/review entry points now routes directly to V3 execution/audit surfaces.
- `sendTurn` for V3 by-id flow now calls V3 turn endpoint (`/v3/.../threads/by-id/{thread_id}/turns`).

### Backend

- V3 execution/audit APIs are the only supported path for active conversation operations.
- V2 thread routes now reject `execution`/`audit` role with `invalid_request`.
- V2 by-id workflow thread endpoints for execution/audit are disabled and point clients to V3.
- V3 execution by-id turn endpoint added for follow-up turns.

### Bootstrap / Config

- execution/audit V2<->V3 gate fields were removed from bootstrap payload.
- frontend env gate keys for execution/audit V3 selection were removed.
- backend config accessors for execution/audit UIUX V3 gates were removed.

## Rollback Policy

- no runtime gate rollback is available for execution/audit.
- rollback is release-level only: deploy previous version or revert commit set.

## Verification Snapshot

- Backend:
  - `backend/tests/unit/test_app_config.py`
  - `backend/tests/unit/test_project_service.py`
  - `backend/tests/integration/test_chat_v2_api.py`
  - `backend/tests/integration/test_chat_v3_api_execution_audit.py`
- Frontend:
  - `npm run test:unit` (full suite)
  - execution/audit routing + V3 store/render integration tests green

