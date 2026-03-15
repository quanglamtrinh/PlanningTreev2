# Source Architecture: CodexMonitor

## Core Conversation Orchestration
- Primary live conversation state and routing lives under `CodexMonitor/src/features/threads/hooks/`.
- Key modules audited:
  - `useThreads.ts`
  - `useThreadsReducer.ts`
  - `useThreadMessaging.ts`
  - `useThreadItemEvents.ts`
  - `useThreadTurnEvents.ts`
  - `useThreadApprovalEvents.ts`
  - `useThreadUserInputEvents.ts`
  - `useThreadEventHandlers.ts`
- Supporting normalization and metadata helpers live in:
  - `CodexMonitor/src/features/threads/utils/threadNormalize.ts`
  - `CodexMonitor/src/features/threads/utils/threadCodexMetadata.ts`
  - `CodexMonitor/src/features/threads/utils/threadRpc.ts`

## Message And Plan Rendering
- Message renderer primitives audited:
  - `CodexMonitor/src/features/messages/components/Messages.tsx`
  - `CodexMonitor/src/features/messages/components/MessageRows.tsx`
  - `CodexMonitor/src/features/messages/components/Markdown.tsx`
- Plan rendering audited:
  - `CodexMonitor/src/features/plan/components/PlanPanel.tsx`
- These modules are responsible for:
  - text streaming presentation
  - markdown and file link rendering
  - reasoning rows
  - tool cards and results
  - plan block rendering
  - rich item grouping

## Streaming And Event Flow
- Frontend conversation code consumes app-server events incrementally and applies item or turn updates into reducer state.
- Event handling is split by concern:
  - turn lifecycle
  - item lifecycle
  - approvals
  - user input
  - queued messaging
- This is not a plain text transcript UI. The UX depends on itemized event application and deterministic reducer updates.

## Runtime Semantics Observed
- Conversation architecture includes semantics for:
  - interrupt and cancel
  - user input requests
  - approvals
  - queued sends
  - turn ownership
  - rich item updates
- Rich state is updated incrementally rather than reconstructed from scratch on every event.

## Native And Tauri Dependencies
- Frontend bridge entry point:
  - `CodexMonitor/src/services/tauri.ts`
- Native conversation and app-server dependencies audited:
  - `CodexMonitor/src-tauri/src/backend/app_server.rs`
  - `CodexMonitor/src-tauri/src/backend/events.rs`
  - `CodexMonitor/src-tauri/src/shared/codex_core.rs`
  - `CodexMonitor/src-tauri/src/shared/process_core.rs`
- These modules include process lifecycle and transport assumptions that do not map directly onto PlanningTree's backend.
- Result: most bridge and app-server integration pieces must be `reimplement_with_reference`, not direct copy.

## Session And Workspace Assumptions
- CodexMonitor conversation runtime is tightly coupled to workspace and native process assumptions.
- Some native behavior supports shared or reused live sessions in ways that conflict with the locked PlanningTree decision to isolate sessions per project or workspace.
- That makes source backend and native process code a behavioral reference, not a drop-in target implementation.

## Source Styling Dependencies
- Source message and plan rendering also depends on CodexMonitor-specific styling and layout assumptions.
- Only conversation-local rendering and styling should be adapted.
- Shell, sidebar, panel, and layout styling must not be pulled in implicitly.
