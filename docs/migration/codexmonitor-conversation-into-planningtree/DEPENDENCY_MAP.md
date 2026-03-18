# Dependency Map

## Frontend State And Contracts
### Existing Anchors
- `frontend/src/api/types.ts`
  - Current source of truth for `ChatSession`, `AskSession`, planning history types, runtime input types, and SSE event payloads.
  - Will remain the compatibility surface until conversation-v2 types fully replace per-feature chat typing.
- `frontend/src/stores/chat-store.ts`
  - Current singleton execution chat state, message upserts, and reset flow.
  - Important because it shows current delta merge assumptions and execution-only command wiring.
- `frontend/src/stores/ask-store.ts`
  - Current singleton ask state, packet status updates, and ask-session event handling.
  - Important because ask packet behavior must survive the migration.
- `frontend/src/api/hooks.ts`
  - Current stream buffering and reconnect behavior for chat, ask, planning, and agent streams.
  - Provides the closest existing target pattern for the future shared conversation stream hook.

### New Foundations Added In Phase 1
- `frontend/src/features/conversation/types.ts`
  - Canonical frontend conversation identity, runtime mode, message part, snapshot, and event envelope contracts.
- `frontend/src/features/conversation/adapters/legacyConversationAdapter.ts`
  - Compatibility layer from current `ChatSession` and `AskSession` into normalized conversation snapshots.
- `frontend/src/stores/conversation-store.ts`
  - Keyed multi-conversation store based on `conversation_id`, with deterministic message and part upsert behavior.

### Planned Frontend Additions That Depend On These Contracts
- `frontend/src/features/conversation/hooks/useConversationStream.ts`
- `frontend/src/features/conversation/actions/useConversationCommands.ts`
- `frontend/src/features/conversation/components/ConversationView.tsx`
- `frontend/src/features/conversation/components/blocks/*`

## Backend Runtime, Gateway, And Session
### Current Runtime Wiring
- `backend/main.py`
  - Currently wires one app-global `CodexAppClient`, `ThreadService`, `ChatService`, `AskService`, and `SplitService`.
  - This is the main architectural blocker for per-project session ownership.
- `backend/services/chat_service.py`
  - Current execution-thread runtime path.
- `backend/services/ask_service.py`
  - Current ask-thread runtime path.
- `backend/services/thread_service.py`
  - Current thread lifecycle dependency used by planning and execution.
- `backend/streaming/sse_broker.py`
  - Existing broker pattern for chat, ask, planning, and agent streams.
  - Likely reuse point for a future conversation broker.

### New Foundation Files Added In Phase 1
- `backend/conversation/contracts.py`
  - Canonical backend identity, runtime mode, event envelope, message, and part contracts.
- `backend/storage/conversation_store.py`
  - Dedicated durable store for conversation records, rich messages, scope index, active stream, and event cursor.
- `backend/storage/storage.py`
  - Now exposes `conversation_store` alongside existing stores.

### Planned Runtime And Gateway Dependencies
- `backend/services/conversation_gateway.py`
  - Request setup path, stream ownership binding, and hot-path forwarding.
- `backend/services/codex_session_manager.py`
  - Per-project or per-workspace session pool and health ownership.
- `backend/services/conversation_context_builder.py`
  - Prompt and context layering from PlanningTree node, task, brief, spec, thread type, runtime mode, and policy state.
- `backend/routes/conversation.py`
  - Parallel conversation-v2 API surface.
- `backend/streaming/conversation_broker.py`
  - Shared event fan-out with `conversation_id`, `stream_id`, and `event_seq`.

## Persistence And Replay
### Current Persistence Dependencies
- `backend/storage/thread_store.py`
  - Holds `planning`, `execution`, and `ask` buckets in `thread_state.json`.
  - Too flat for CodexMonitor-style rich replay, but still a migration dependency for wrapper state and compatibility reads.
- `backend/storage/chat_store.py`
  - Stores `chat_state.json`; remains legacy compatibility surface only.
- `backend/storage/file_utils.py`
  - Atomic JSON write utilities and ID generation used by both old and new stores.

### New Durable Conversation Path
- `backend/storage/conversation_store.py`
  - Persists `conversation_state.json`.
  - Durable truth model includes:
    - `scope_index`
    - `ConversationRecord`
    - `ConversationMessage[]`
    - message parts
    - active stream ownership
    - reconnect cursor
- `frontend/src/features/conversation/adapters/legacyConversationAdapter.ts`
  - Bridges old simple sessions into the new snapshot shape during dual-path operation.

### Replay And Recovery Dependencies
- `conversation_id`
  - Stable durable identity per `(project_id, node_id, thread_type)` in this migration phase.
- `stream_id`
  - Active stream owner; used to reject stale updates.
- `event_seq`
  - Reconnect cursor only; not replay truth.
- Normalized message and part order
  - Required to rebuild rich UI without replaying raw event logs.

## Styling And Rendering
### Current PlanningTree Rendering Anchors
- `frontend/src/features/breadcrumb/ChatPanel.tsx`
- `frontend/src/features/breadcrumb/AskPanel.tsx`
- `frontend/src/features/breadcrumb/PlanningPanel.tsx`
- `frontend/src/features/breadcrumb/ChatPanel.module.css`
- `frontend/src/features/breadcrumb/AskPanel.module.css`
- `frontend/src/features/breadcrumb/PlanningPanel.module.css`

### Source Renderer Dependencies To Reuse Carefully
- `CodexMonitor/src/features/messages/components/Messages.tsx`
- `CodexMonitor/src/features/messages/components/MessageRows.tsx`
- `CodexMonitor/src/features/messages/components/Markdown.tsx`
- `CodexMonitor/src/features/plan/components/PlanPanel.tsx`

### Styling Rules For This Migration
- Preserve PlanningTree wrapper layout and CSS modules.
- Move only conversation-local rendering styles.
- Do not import CodexMonitor shell, sidebar, or panel layout CSS.
- Treat shell-level dependencies as `adapt_before_migrate`, `stub_temporarily`, or `defer`, never implicit imports.

## PlanningTree Wrapper Dependencies
### Breadcrumb Host
- `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx`
  - Owns tab selection, current thread embedding, composer seeding, and current per-tab stream hook wiring.
  - This remains the integration host during the migration.

### Ask Wrapper Dependencies
- `frontend/src/features/breadcrumb/AskPanel.tsx`
  - Owns ask read-only notices, reset flow, composer shell, and packet-sidecar placement.
- `frontend/src/features/breadcrumb/DeltaContextCard.tsx`
  - Must remain functional even after ask message rendering moves to the shared conversation surface.

### Planning Wrapper Dependencies
- `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - Owns split action buttons, planning history framing, and split payload rendering.
- `frontend/src/stores/project-store.ts`
  - Owns planning history, connection status, split actions, and document reloads that planning still depends on.

### Execution Wrapper Dependencies
- `frontend/src/features/breadcrumb/ChatPanel.tsx`
  - Owns current execution composer shell, reset button, and loading or empty states.
- `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx`
  - Owns execution action buttons, planner-input modal, plan card, and execution-specific framing above the current chat body.

### Wrapper Constraint
- The shared conversation surface must be embedded inside these wrappers.
- It must not erase packet-sidecar behavior, planning split controls, execution action cards, or breadcrumb navigation behavior.
