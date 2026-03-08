# Dependency Map — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

---

## Backend Dependencies (Python)

### Runtime Dependencies (`backend/requirements.txt`)

| Package | Purpose | Rebuild Status |
|---|---|---|
| fastapi | HTTP framework, routing, dependency injection | REPLACE with FastAPI (keep) |
| uvicorn | ASGI server | KEEP |
| pydantic | Data validation, request/response models | KEEP |
| openai | OpenAI API client (used by Codex subprocess or direct calls) | KEEP (OpenAI Responses API for splits) |
| langgraph | State graph for split flow (generate→parse→normalize→drift→retry) | REMOVE |
| langchain | LLM chain utilities used by LangGraph nodes | REMOVE |
| langchain-community | Additional LC integrations (SqliteSaver checkpointer) | REMOVE |
| httpx | Async HTTP client (used for internal requests if any) | KEEP (optional) |
| python-multipart | Form data parsing for FastAPI | KEEP (if needed) |
| aiofiles | Async file I/O | KEEP |

### Dev Dependencies

| Package | Purpose |
|---|---|
| pytest | Test runner |
| pytest-asyncio | Async test support |
| httpx | Test client for FastAPI (TestClient) |

---

## Frontend Dependencies (npm)

### Runtime Dependencies (`frontend/package.json`)

| Package | Version | Purpose | Rebuild Status |
|---|---|---|---|
| react | 18.3.1 | UI framework | KEEP |
| react-dom | 18.3.1 | React DOM renderer | KEEP |
| reactflow | 11.11.4 | Graph visualization | REPLACE with @xyflow/react |
| zustand | — | State management | KEEP (new — not in legacy) |
| react-router-dom | — | Routing | NEW |

### Dev Dependencies

| Package | Version | Purpose | Rebuild Status |
|---|---|---|---|
| typescript | 5.6.2 | Type checking | KEEP |
| vite | 5.4.8 | Build tool and dev server | KEEP |
| @vitejs/plugin-react | 4.3.2 | React support for Vite | KEEP |
| vitest | 2.1.5 | Unit test runner | KEEP |
| playwright | 1.55.0 | E2E browser testing | KEEP |
| @testing-library/react | 16.3.0 | React component testing | KEEP |
| jsdom | 26.1.0 | DOM environment for unit tests | KEEP |

---

## External Services and Processes

### Codex App Server (Subprocess)

- **What:** External binary (shipped with VSCode Codex extension or installed separately)
- **How:** Spawned as child process in `backend/codex_app_client.py`
- **Transport:** stdio — JSON-RPC messages over stdin/stdout
- **Discovery:** Checked in PATH, then VSCode extension directory (`~/.vscode/extensions/github.copilot-*`)
- **Used for:** All planning operations (split prompts), gate execution, chat sessions, node title generation
- **Rebuild status:** KEEP for chat (Codex app server threads). REPLACE for splits (OpenAI Responses API directly).

### OpenAI API

- **What:** OpenAI REST API
- **How:** Via `openai` Python SDK (currently used by Codex subprocess internally; API key passed through)
- **Auth:** `OPENAI_API_KEY` environment variable
- **Rebuild status:** KEEP. Splits will call OpenAI Responses API directly using `openai` SDK.

### Google Fonts (CDN)

- **What:** Inter and JetBrains Mono font families
- **How:** CDN links in `frontend/index.html`
- **Rebuild status:** KEEP (same fonts, same approach).

---

## Internal Module Dependency Graph

### Backend

```
main.py
  └── CodexAppClient          (codex_app_client.py)
  └── Storage                 (storage.py)
  └── LockManager             (lock_manager.py)
  └── LangGraph SqliteSaver   (langchain_community)  ← REMOVE
  └── WorkerAdapter           (worker_adapter.py)
        └── CodexAppClient
        └── split_planner.py
        └── context_projection.py
  └── Orchestrator            (orchestrator.py)
        └── Storage
        └── LockManager
        └── WorkerAdapter
        └── split_graph.py    ← REMOVE
        └── fsm.py
  └── LangGraphRunner         (langgraph_runner.py)  ← REMOVE
        └── Orchestrator
        └── Storage
  └── ChatService             (chat_service.py)
        └── Storage
        └── CodexAppClient
        └── ChatEventBroker
  └── Routers
        └── projects.py  → LangGraphRunner
        └── chat.py      → ChatService
        └── events.py    → Storage (audit.ndjson)  ← REMOVE
        └── metrics.py   → Orchestrator             ← REMOVE
```

### Frontend

```
main.tsx
  └── App.tsx
        └── sseManager.ts        ← simplified in rebuild
        └── store.ts             ← REMOVE (audit event store)
        └── client.ts            → backend HTTP API
        └── contracts.ts         → type definitions
        └── selection.ts         → node selection logic
        └── WorkflowGraph.tsx
        └── ChatPanel.tsx
        └── BreadcrumbView.tsx
        └── NodeDetailPanel.tsx
        └── VersionNavigator.tsx ← REMOVE
        └── ReconfirmationPanel.tsx ← REMOVE
        └── ContextLens.tsx      ← REMOVE
```

---

## Configuration / Environment Dependencies

| Env Var | Used By | Effect |
|---|---|---|
| OPENAI_API_KEY | Codex subprocess (indirectly) | Required for AI operations |
| PLANNINGTREE_DATA_ROOT | storage.py | Override default data directory |
| PLANNINGTREE_CODEX_CMD | codex_app_client.py | Override Codex binary path |
| PLANNINGTREE_PLAN_TIMEOUT_SEC | orchestrator.py | Timeout for plan operations (default 60s) |
| PLANNINGTREE_SPLIT_TIMEOUT_SEC | orchestrator.py | Timeout for split operations (default 120s) |
| PLANNINGTREE_NODE_TITLE_TIMEOUT_SEC | orchestrator.py | Timeout for title generation (default 20s) |
| PLANNINGTREE_INTERPRETER_MODE | worker_adapter.py | Codex interpreter mode |

---

## Coupling Hotspots

| Coupling | Description | Impact on Rebuild |
|---|---|---|
| Orchestrator → Gate system | Gate planning, gate running, rollback are in orchestrator.py alongside core node CRUD | Removing gates requires carving gate logic out of orchestrator carefully |
| Storage → Audit | audit.ndjson writes are embedded throughout storage.py mutation methods | Removing audit requires systematically stripping audit calls |
| WorkerAdapter → Gate config | `worker_adapter.py` builds gate execution configs mixed with split/plan configs | Gate config removal simplifies this module significantly |
| App.tsx → Everything | All state, all event handlers, all SSE, all API calls in one 1,554-line component | Decompose into Zustand stores + feature components |
| styles.css → All UI | 2,591 lines of global CSS; no scoping | Migrate to CSS Modules per component |
