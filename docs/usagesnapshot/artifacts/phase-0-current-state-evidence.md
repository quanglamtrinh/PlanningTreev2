# Phase 0 Current-State Evidence

Status: completed.

Captured on: 2026-04-06.

## Backend baseline evidence

- Existing codex snapshot route is present:
  - `backend/routes/codex.py:14` -> `@router.get("/codex/account")`
- Existing codex SSE route is present:
  - `backend/routes/codex.py:19` -> `@router.get("/codex/events")`
- Usage-local route does not exist yet:
  - no match for `/codex/usage/local` in `backend/routes/codex.py`

## Frontend baseline evidence

- Existing app routes include graph and chat surfaces only:
  - `frontend/src/App.tsx:12` -> `path="/"` (GraphWorkspace)
  - `frontend/src/App.tsx:14` -> `.../chat`
  - `frontend/src/App.tsx:18` -> `.../chat-v2`
- `/usage-snapshot` route does not exist yet:
  - no match in `App.tsx`, `Sidebar.tsx`, `Layout.tsx`

## Existing sidebar usage UX baseline

- Sidebar currently renders session/weekly/credits usage block:
  - `frontend/src/features/graph/Sidebar.tsx:292` -> `usageBlock`
  - `frontend/src/features/graph/Sidebar.tsx:294` -> `Session`
  - `frontend/src/features/graph/Sidebar.tsx:308` -> `Weekly`
  - `frontend/src/features/graph/Sidebar.tsx:324` -> `creditsLabel`

## Existing data-flow baseline

- Frontend codex store reads account snapshot from `/v1/codex/account`:
  - `frontend/src/api/client.ts:282`
  - `frontend/src/api/client.ts:283`
- Frontend codex store subscribes to `/v1/codex/events`:
  - `frontend/src/stores/codex-store.ts:119`

## Test infrastructure baseline

- Frontend unit and E2E scripts are already configured:
  - `frontend/package.json:12` -> `test:unit`
  - `frontend/package.json:14` -> `test:e2e`
  - `frontend/package.json:34` -> `@playwright/test`
- Existing E2E folder is available:
  - `frontend/tests/e2e/core-graph.spec.ts`

## Compatibility conclusion

- Adding `GET /v1/codex/usage/local` is additive and does not conflict with existing codex account/SSE flows.
- Adding `/usage-snapshot` route and a new sidebar button is additive and compatible with current shell routing.
- Required unit/integration/E2E layers already exist, so Phase 1+ can implement without introducing a new test framework.
