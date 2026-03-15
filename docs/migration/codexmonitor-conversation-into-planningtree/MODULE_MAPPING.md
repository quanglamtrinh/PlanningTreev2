# Module Mapping

## Classification Key
- `direct_migrate`: can move with minor adaptation
- `adapt_before_migrate`: target contracts or wrappers must exist first
- `reimplement_with_reference`: behavior should be preserved, but code should be rebuilt for PlanningTree
- `stub_temporarily`: visible placeholder is acceptable for an interim cutover
- `defer`: outside the current migration baseline

## Source Conversation Orchestration
| Source Module | Source Path | Target Module | Target Path | Classification | Purpose | Dependency Notes | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| `useThreads.ts` | `CodexMonitor/src/features/threads/hooks/useThreads.ts` | `useConversationController` | `frontend/src/features/conversation/hooks/useConversationController.ts` | reimplement_with_reference | Top-level conversation orchestration and composition | Must orchestrate keyed state, stream lifecycle, and command surfaces without importing CodexMonitor shell assumptions | High | 3 |
| `useThreadsReducer` | `CodexMonitor/src/features/threads/hooks/useThreadsReducer.ts` | `conversation-store` | `frontend/src/stores/conversation-store.ts` | reimplement_with_reference | Keyed conversation state and deterministic upserts | Replaces singleton ask/chat ownership and must support multiple active conversations | High | 1 |
| `useThreadEventHandlers` | `CodexMonitor/src/features/threads/hooks/useThreadEventHandlers.ts` | `useConversationStream` | `frontend/src/features/conversation/hooks/useConversationStream.ts` | reimplement_with_reference | Stream event dispatch, buffering, and reconnect handoff | Must work with `conversation_id`, `stream_id`, `event_seq`, and thin gateway SSE | High | 2 |
| `useThreadMessaging` | `CodexMonitor/src/features/threads/hooks/useThreadMessaging.ts` | `useConversationCommands` | `frontend/src/features/conversation/actions/useConversationCommands.ts` | adapt_before_migrate | `send`, `cancel`, `retry`, `continue`, `regenerate` command surface | Depends on gateway endpoints, lineage rules, and stream ownership | High | 4 |
| `useThreadItemEvents` | `CodexMonitor/src/features/threads/hooks/useThreadItemEvents.ts` | `codexEventAdapter` | `frontend/src/features/conversation/adapters/codexEventAdapter.ts` | reimplement_with_reference | Incremental item updates into normalized message parts | Depends on phase-1 event schema and stale-stream rejection rules | High | 5 |
| `useThreadTurnEvents` | `CodexMonitor/src/features/threads/hooks/useThreadTurnEvents.ts` | `conversationTurnReducer` | `frontend/src/features/conversation/reducer/conversationTurnReducer.ts` | reimplement_with_reference | Turn lifecycle, active turn ownership, and lineage updates | Must key off `conversation_id`, `turn_id`, and `stream_id` instead of source reducer slices | High | 5 |
| `useThreadApprovalEvents` | `CodexMonitor/src/features/threads/hooks/useThreadApprovalEvents.ts` | `codexEventAdapter` | `frontend/src/features/conversation/adapters/codexEventAdapter.ts` | reimplement_with_reference | Approval request and approval resolution handling | Depends on durable approval state and eager persistence rules | High | 5 |
| `useThreadUserInputEvents` | `CodexMonitor/src/features/threads/hooks/useThreadUserInputEvents.ts` | `codexEventAdapter` | `frontend/src/features/conversation/adapters/codexEventAdapter.ts` | reimplement_with_reference | Runtime input request and answer handling | Must align with PlanningTree native input UX and replay requirements | High | 5 |

## Renderers
| Source Module | Source Path | Target Module | Target Path | Classification | Purpose | Dependency Notes | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| `Messages` | `CodexMonitor/src/features/messages/components/Messages.tsx` | `ConversationView` | `frontend/src/features/conversation/components/ConversationView.tsx` | adapt_before_migrate | Shared message list and rich block rendering shell | Must be detached from CodexMonitor shell layout and run on normalized message parts | Medium | 3 |
| `MessageRows` | `CodexMonitor/src/features/messages/components/MessageRows.tsx` | `ConversationBlocks` | `frontend/src/features/conversation/components/blocks/*` | adapt_before_migrate | Per-item rows for reasoning, tools, plans, diffs, and status blocks | Depends on deterministic part ordering and block-level replay fidelity | Medium | 5 |
| `Markdown` | `CodexMonitor/src/features/messages/components/Markdown.tsx` | `ConversationMarkdown` | `frontend/src/features/conversation/components/ConversationMarkdown.tsx` | direct_migrate | Markdown rendering helper for assistant and tool output | Low shell coupling; can be moved once conversation-local styling exists | Low | 3 |
| `PlanPanel` | `CodexMonitor/src/features/plan/components/PlanPanel.tsx` | `PlanBlock` | `frontend/src/features/conversation/components/blocks/PlanBlock.tsx` | reimplement_with_reference | Structured plan rendering and plan step grouping | Must render from normalized plan parts and live inside PlanningTree wrappers | Medium | 5 |

## Adapters And Normalization
| Source Module | Source Path | Target Module | Target Path | Classification | Purpose | Dependency Notes | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| `threadNormalize` | `CodexMonitor/src/features/threads/utils/threadNormalize.ts` | `legacyConversationAdapter` | `frontend/src/features/conversation/adapters/legacyConversationAdapter.ts` | adapt_before_migrate | Bridge current PlanningTree simple sessions into normalized conversation snapshots | Transitional adapter only; removed when all threads are on conversation-v2 | Medium | 1 |
| `threadRpc` | `CodexMonitor/src/features/threads/utils/threadRpc.ts` | `conversation client surface` | `frontend/src/api/client.ts` and `backend/routes/conversation.py` | reimplement_with_reference | Command and event transport contract reference | Source implementation is Tauri-specific and must be recast as frontend-to-gateway HTTP plus SSE | High | 2 |
| `threadCodexMetadata` | `CodexMonitor/src/features/threads/utils/threadCodexMetadata.ts` | `conversation context builder` | `backend/services/conversation_context_builder.py` | reimplement_with_reference | Build system prompt and request metadata from thread context | Must layer PlanningTree task, brief, spec, thread type, runtime mode, and tool policy | High | 2 |

## Backend, Session, And Gateway
| Source Module | Source Path | Target Module | Target Path | Classification | Purpose | Dependency Notes | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| `tauri.ts` | `CodexMonitor/src/services/tauri.ts` | `conversation gateway client layer` | `backend/services/conversation_gateway.py` and `frontend/src/api/client.ts` | reimplement_with_reference | Replace native bridge transport and request plumbing | Frontend must call thin gateway endpoints instead of Tauri commands | High | 2 |
| `app_server.rs` | `CodexMonitor/src-tauri/src/backend/app_server.rs` | `codex_session_manager` | `backend/services/codex_session_manager.py` | reimplement_with_reference | Process lifecycle and runtime session ownership | Must honor project isolation instead of source live shared session assumptions | High | 2 |
| `events.rs` | `CodexMonitor/src-tauri/src/backend/events.rs` | `conversation broker` | `backend/streaming/conversation_broker.py` | reimplement_with_reference | Runtime event forwarding and broker fan-out reference | Must stay thin on the hot path and preserve stream ownership metadata | High | 2 |
| `codex_core.rs` | `CodexMonitor/src-tauri/src/shared/codex_core.rs` | `conversation runtime contracts` | `backend/conversation/contracts.py` | reimplement_with_reference | Runtime thread and request semantics reference | Use as behavior reference only; do not copy native assumptions directly | Medium | 1 |

## Legacy Target Stores And Panels Affected
This section is target-first on purpose. These modules already exist in PlanningTree and must be wrapped, preserved, or retired carefully during cutover.

| Current Target Module | Current Path | Migration Treatment | Planned Landing Or Role | Why It Matters | Risk | Phase |
|---|---|---|---|---|---|---|
| `chat-store` | `frontend/src/stores/chat-store.ts` | adapt then retire | compatibility path until execution cutover lands on `conversation-store` | Owns singleton execution chat state today and cannot support keyed concurrent conversations | High | 1-3 |
| `ask-store` | `frontend/src/stores/ask-store.ts` | adapt then retire | compatibility path until ask cutover lands on `conversation-store` | Owns singleton ask state today and must preserve packet-sidecar behavior during dual path | High | 1-4 |
| `project-store` planning history and agent state | `frontend/src/stores/project-store.ts` | preserve wrapper state, adapt boundaries | continues to own planning history wrappers and artifact loading until planning embedding is complete | Planning split controls and wrapper state should not be collapsed into generic conversation state too early | High | 4 |
| `ChatPanel` | `frontend/src/features/breadcrumb/ChatPanel.tsx` | wrap then replace body | becomes the execution host for the shared conversation surface | Execution is the first visible cutover and must keep current framing, buttons, and empty states stable | Medium | 3 |
| `AskPanel` | `frontend/src/features/breadcrumb/AskPanel.tsx` | keep wrapper, replace message body | becomes the ask host for the shared conversation surface plus packet sidecar | Ask-specific notices and delta context packet cards must remain intact | Medium | 4 |
| `PlanningPanel` | `frontend/src/features/breadcrumb/PlanningPanel.tsx` | keep wrapper, embed shared surface selectively | remains the planning host with split actions and planning history framing | Split actions are product semantics, not generic conversation controls | High | 4 |
| `BreadcrumbWorkspace` | `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx` | adapt stream wiring and tab routing | remains the tab and thread container | It currently selects tabs, seeds execution composer state, and wires ask/chat/planning streams separately | High | 3-4 |
| `api/hooks.ts` | `frontend/src/api/hooks.ts` | parallelize then converge | existing per-feature stream hooks coexist until `useConversationStream` is adopted | Current reconnect and buffering logic is a strong reference point for execution-first cutover | Medium | 2-3 |
