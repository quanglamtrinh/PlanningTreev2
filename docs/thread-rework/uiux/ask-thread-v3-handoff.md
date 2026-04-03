# Ask Thread V3 Handoff

Date: 2026-04-03

Status: planning handoff for ask-thread V3 migration (implementation not started).

## 1. Scope and goal

- Target thread lane: `ask` (`ask_planning` role).
- Goal: move ask from legacy V1 chat pipeline to V3 conversation pipeline.
- Must not regress: execution/audit V3 hard-cutover behavior already completed.

## 2. Current architecture (actual codebase state)

### Frontend routing and surfaces

- `ask` currently resolves to legacy `/chat` surface.
- `execution` and `audit` resolve to `/chat-v2` with V3 feed.
- Main routing decision lives in `frontend/src/features/conversation/surfaceRouting.ts`.

### Ask lane frontend runtime

- Ask lane uses legacy store: `frontend/src/stores/chat-store.ts`.
- Ask lane UI is rendered by `frontend/src/features/breadcrumb/BreadcrumbChatView.tsx` with:
  - `MessageFeed`
  - `ComposerBar`
  - `FrameContextFeedBlock`
- API client calls used by ask are V1 routes in `frontend/src/api/client.ts`:
  - `getChatSession`
  - `sendChatMessage`
  - `resetChatSession`
  - SSE via `/v1/.../chat/events`

### Backend routes and services

- Legacy ask API is active in `backend/routes/chat.py` (`/v1/.../chat/*`).
- V2 thread routes in `backend/routes/chat_v2.py` still support `ask_planning`.
- V3 by-id routes in `backend/routes/workflow_v3.py` currently support only execution/audit semantics.

### Existing V3 contract constraints

- `ThreadLaneV3` is currently `execution | audit` only (`frontend/src/api/types.ts`).
- V3 item semantics (`message/reasoning/tool/explore/userInput/review/diff/status/error`) are already implemented for execution/audit feed.

## 3. What is already reusable for ask migration

- V3 store patterns:
  - snapshot apply
  - incremental patch apply
  - version guard + reconnect/reload fallback
- V3 UI pipeline:
  - `MessagesV3`
  - item-kind renderer model
  - view-state persistence pattern (thread-scoped localStorage)
- V3 backend stream model:
  - by-id snapshot + incremental event stream
  - dedicated action endpoints pattern

## 4. Gaps specific to ask

- Ask still depends on legacy `ChatSession` model and `chat-store`.
- Ask uses V1 SSE event shape, not V3 envelope shape.
- Ask behavior has shaping-specific UX tied to `FrameContextFeedBlock` and existing composer states.
- Read-only rules around post-execution ask behavior are enforced in legacy services/tests and need explicit parity mapping in V3.

## 5. Planning constraints

- Keep execution/audit stable and untouched except where shared primitives must be generalized.
- No hidden behavior drift in ask:
  - semantics
  - interaction
  - micro-behavior
- Prefer additive migration with explicit parity gate before hard cutover.
- Keep rollback strategy explicit for ask migration phase (flagged or release rollback), decide early and freeze.

## 6. Recommended planning decisions to lock before implementation

- V3 contract for ask:
  - keep `ask_planning` as thread role and map to a V3 lane key, or add dedicated `ask` lane in V3 type system.
- Endpoint strategy:
  - extend existing `/v3/.../threads/by-id/*` for ask
  - or add ask-specific V3 route namespace.
- UI strategy:
  - unify ask into `MessagesV3` directly
  - or keep a thin ask-specific wrapper that composes V3 feed with shaping side panels.
- Rollout strategy:
  - phased flag rollout first, then hard cutover
  - or direct hard cutover for ask (higher risk).

## 7. Baseline test surfaces to preserve while planning

- Frontend:
  - `frontend/tests/unit/BreadcrumbChatView.test.tsx`
  - `frontend/tests/unit/chat-store.test.ts`
  - `frontend/tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx` (ask route expectations)
- Backend:
  - `backend/tests/integration/test_chat_api.py`
  - `backend/tests/unit/test_chat_service.py`
  - `backend/tests/unit/test_thread_readonly.py`
  - `backend/tests/integration/test_lifecycle_e2e.py`

## 8. Definition of done for the upcoming ask V3 plan (proposal)

- Ask lane has a frozen V3 contract appendix.
- Ask lane has V3 backend read/stream/action path with parity tests.
- Ask lane has V3 frontend store + render path and parity tests.
- Parity gate report for ask is green.
- Cutover and rollback policy for ask is documented and drill-verified.

