# System Overview — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

---

## Stack

| Layer | Technology | Version |
|---|---|---|
| Backend language | Python | 3.9+ |
| HTTP framework | FastAPI | latest |
| ASGI server | Uvicorn | latest |
| Data validation | Pydantic | v2 |
| AI orchestration | LangGraph + LangChain | latest |
| AI subprocess | Codex app server | external binary |
| Persistence | File-based JSON + NDJSON | — |
| Real-time transport | Server-Sent Events (SSE) | — |
| Auth | None | — |
| Frontend framework | React | 18.3.1 |
| Frontend language | TypeScript | 5.6.2 |
| Build tool | Vite | 5.4.8 |
| Graph visualization | ReactFlow | 11.11.4 |
| Testing (frontend) | Vitest 2.1.5 + Playwright 1.55 | — |
| Testing (backend) | pytest / unittest | — |

---

## Repository Layout

```
PlanningTreeCodex/
├── backend/              # 68 Python files — FastAPI app
│   ├── main.py           # App factory, entry point
│   ├── routers/          # HTTP route handlers
│   └── *.py              # Flat module layout (no sub-packages)
├── frontend/             # React SPA
│   ├── src/
│   │   ├── app/          # App.tsx root component
│   │   ├── features/     # Feature components
│   │   └── *.ts(x)       # Shared utilities, types, stores
│   └── tests/            # Vitest unit + Playwright E2E
├── scripts/              # Dev, test, and helper scripts
└── docs/                 # Canonical rebuild specifications
```

---

## Entry Points

### Backend
- File: `backend/main.py`
- Function: `create_app() → FastAPI`
- Server: `uvicorn backend.main:app --reload --port 8000`

### Frontend
- File: `frontend/index.html` → `src/main.tsx`
- Root component: `src/app/App.tsx`
- Dev server: `vite` on port 5173

### Dev Scripts
- `python scripts/dev.py` — cross-platform, starts both servers
- `powershell scripts/dev.ps1` — Windows only
- `powershell scripts/start-backend.ps1` / `start-frontend.ps1` — individual servers

---

## Boot / Initialization Flow

### Backend Boot (`backend/main.py → create_app()`)

1. Configure logging (structured, configurable level)
2. Register CORS middleware (allow all origins — local-only, no auth)
3. Initialize `CodexAppClient` — discovers `codex` binary from PATH or VSCode extensions dir; opens stdio JSON-RPC subprocess
4. Initialize `Storage` — resolves `PLANNINGTREE_DATA_ROOT` (defaults to `%APPDATA%\PlanningTree\users\local\projects` on Windows); ensures directories exist
5. Initialize `LockManager` — file-based mutex per project, 60s stale lock timeout
6. Initialize `LangGraph SqliteSaver` — checkpoint store for split state graphs
7. Initialize `WorkerAdapter` — wraps CodexAppClient, builds Codex invocation configs per operation type
8. Initialize `Orchestrator` — core business logic; holds references to storage, lock manager, worker adapter
9. Initialize `LangGraphRunner` — wraps orchestrator operations with: lock acquire, LangGraph graph execution, retry (3 attempts, exponential backoff), event publishing
10. Initialize `ChatService` + `ChatEventBroker` — per-node chat sessions; pub/sub for SSE streaming
11. Register 4 FastAPI routers: `projects`, `chat`, `events`, `metrics`
12. Return app to Uvicorn

### Frontend Boot (`main.tsx → App.tsx`)

1. React 18 root created, `<App>` rendered inside `<ErrorBoundary>`
2. `App.tsx` initializes all state with `useState` hooks (projects, snapshot, theme, SSE state, UI flags)
3. `useEffect` on mount: fetch project list from `GET /v1/projects`
4. Theme loaded from `localStorage['planningtree.theme']`
5. SSE connection established via `sseManager.ts` to `GET /v1/projects/{id}/events`
6. On SSE event: apply audit event to state via `store.ts:applyIncomingEvent()`, refresh snapshot if needed

---

## Architecture Style

**Monolith.** Single FastAPI process + single React SPA.

- Backend: flat Python package (no sub-packages below `routers/`)
- Frontend: flat `src/` with a `features/` subdirectory
- No microservices, no separate workers, no message queues
- All state held in one process; persistence on local filesystem
- Codex app server is an external subprocess (not part of the main process)
- All long-running operations (split, plan gates, gate run) are synchronous within the request lifecycle, with timeouts enforced at the service level

---

## Background Jobs / Workers / Queues / WebSockets

**None of the above.**

- No Celery, Redis, Bull, or any queue system
- No WebSocket connections (SSE only)
- No cron jobs or schedulers
- Concurrency: one mutation per project at a time, enforced by file-based lock
- Long operations (split: up to 120s, plan: up to 60s) block the request thread with a timeout

---

## Runtime Environment

- **OS:** Windows primary (dev), cross-platform capable
- **Data root:** `%APPDATA%\PlanningTree\users\local\projects` (Windows) — configurable
- **Backend port:** 8000 (hardcoded in scripts, configurable)
- **Frontend port:** 5173 (Vite default)
- **Codex binary:** discovered from PATH or VSCode extensions; configurable via env var
