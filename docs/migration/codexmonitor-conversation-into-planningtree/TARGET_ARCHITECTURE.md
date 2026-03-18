# Target Architecture: PlanningTreeMain

## Current Frontend Structure
- Breadcrumb host and thread embedding points:
  - `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx`
  - `frontend/src/features/breadcrumb/AskPanel.tsx`
  - `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - `frontend/src/features/breadcrumb/ChatPanel.tsx`
- Current thread-adjacent state stores:
  - `frontend/src/stores/chat-store.ts`
  - `frontend/src/stores/ask-store.ts`
- Current API type surface:
  - `frontend/src/api/types.ts`

## Current Backend Structure
- App entry and service wiring:
  - `backend/main.py`
- Current storage surface:
  - `backend/storage/storage.py`
  - `backend/storage/thread_store.py`
  - `backend/storage/chat_store.py`
- Current service split:
  - `backend/services/chat_service.py`
  - `backend/services/ask_service.py`
- Current backend architecture does not yet expose a shared conversation gateway or session pool.

## Existing Product Model Strengths
- PlanningTree already has:
  - breadcrumb-based embedding
  - ask thread concept
  - planning thread concept
  - execution thread concept
  - task, brief, and spec documents available as context
- These product concepts should remain intact and become inputs to request context building.

## Current Limitations
- Frontend state is singleton by feature, not keyed by conversation identity.
- Backend does not yet have a per-project session manager.
- Persistence is too flat for rich conversation replay.
- Existing event models are chat-specific, ask-specific, and planning-specific instead of converging on one shared conversation schema.
- `thread_state.json` stores current thread buckets but does not preserve the rich metadata required for CodexMonitor-like replay.

## Gaps Vs Target Design
- Need one canonical `conversation_id` per `(project_id, node_id, thread_type)` tuple.
- Need separate `runtime_mode` from `thread_type`.
- Need normalized rich messages as the durable record of truth.
- Need stream ownership and stale-stream rejection rules.
- Need reconnect and replay semantics keyed by conversation identity.
- Need a shared frontend conversation store with keyed state.
- Need a thin backend gateway and per-project session pool.

## Target Fit
- PlanningTree is structurally ready for the migration if the conversation architecture is upgraded first.
- The current target is not ready for a direct visual copy of CodexMonitor because the runtime contracts underneath are still too coarse.
