# Migration Overview

## Goal
- Reuse CodexMonitor's core conversation UX, streaming feel, plan semantics, and custom message rendering inside PlanningTree threads.

## In Scope
- Shared conversation surface embedded inside ask, planning, and execution threads.
- Conversation identity, contracts, gateway, session ownership, persistence, replay, and concurrency.
- Rich normalized message persistence capable of reconstructing the UI after reload.

## Out Of Scope
- CodexMonitor app shell
- sidebar
- dashboard and home shell
- terminal dock
- file tree or browser
- updater
- dictation
- secondary non-chat panels
- writing chat output back into PlanningTree breadcrumb artifacts

## Source Summary
- CodexMonitor frontend conversation orchestration lives primarily under:
  - `src/features/threads/hooks/`
  - `src/features/messages/components/`
  - `src/features/plan/components/`
- Conversation state is reducer-driven, event-heavy, and optimized for incremental updates.
- Native transport and app-server wiring are Tauri-backed under:
  - `src/services/tauri.ts`
  - `src-tauri/src/backend/app_server.rs`
  - `src-tauri/src/shared/codex_core.rs`

## Target Summary
- PlanningTree already has the correct product containers:
  - `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx`
  - `frontend/src/features/breadcrumb/AskPanel.tsx`
  - `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - `frontend/src/features/breadcrumb/ChatPanel.tsx`
- Thread persistence exists today in `backend/storage/thread_store.py`.
- Current chat and ask client state is singleton-based:
  - `frontend/src/stores/chat-store.ts`
  - `frontend/src/stores/ask-store.ts`
- Backend still exposes separate service paths instead of a conversation gateway:
  - `backend/services/chat_service.py`
  - `backend/services/ask_service.py`
  - `backend/main.py`

## Success Criteria
- The target stays runnable after every phase.
- Execution becomes the first visible cutover on the new conversation path.
- Ask and planning reuse the same shared conversation surface while preserving PlanningTree wrappers.
- Rich normalized persistence is sufficient for replay after reload.
- Multiple threads can stream concurrently without cross-cancel or identity corruption.

## Rollout Strategy
- Complete Phase 0 and Phase 1 before broad UI migration.
- Build gateway and session manager in parallel with the old path.
- Cut over execution first, then ask, then planning.
- Keep rollback options until Phase 6 cleanup gates pass.
