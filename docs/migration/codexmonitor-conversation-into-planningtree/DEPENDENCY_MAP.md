# Dependency Map

## Frontend Dependencies
- Existing thread hosts:
  - `frontend/src/features/breadcrumb/AskPanel.tsx`
  - `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - `frontend/src/features/breadcrumb/ChatPanel.tsx`
- Existing client state:
  - `frontend/src/stores/chat-store.ts`
  - `frontend/src/stores/ask-store.ts`
- Existing API surface:
  - `frontend/src/api/client.ts`
  - `frontend/src/api/types.ts`

## Backend Dependencies
- Current app wiring:
  - `backend/main.py`
- Current thread persistence:
  - `backend/storage/thread_store.py`
  - `backend/storage/chat_store.py`
  - `backend/storage/storage.py`
- Current services that will eventually route through the gateway:
  - `backend/services/chat_service.py`
  - `backend/services/ask_service.py`

## Stores, Hooks, And Services To Introduce
- `frontend/src/stores/conversation-store.ts`
- `frontend/src/features/conversation/types.ts`
- `frontend/src/features/conversation/adapters/legacyConversationAdapter.ts`
- `backend/conversation/contracts.py`
- `backend/storage/conversation_store.py`

## Gateway Dependencies
- conversation identity resolution
- request-context builder
- session acquisition and ownership
- SSE or event broker forwarding
- normalized persistence queue

## Session Manager Dependencies
- project-scoped lock registry from `backend/storage/project_locks.py`
- project metadata from `backend/storage/project_store.py`
- workspace root resolution from project records
- process lifecycle and health checks for `codex-app-server`

## Persistence Dependencies
- `backend/storage/file_utils.py` for atomic writes
- project-scoped directories under `projects/<project_id>/`
- durable storage for:
  - conversation record
  - messages
  - parts
  - lineage
  - reconnect cursor

## Styling Dependencies
- conversation-local CSS only
- no CodexMonitor shell or panel styling
- preserve PlanningTree wrapper layout and CSS modules

## Hidden Non-UI Dependencies
- stream ownership rules
- stale-stream rejection rules
- turn lineage model
- reconnect cursor handling
- compatibility adapters for current simple message state
- explicit no-shell-creep classification for any source dependency that crosses beyond the conversation surface
