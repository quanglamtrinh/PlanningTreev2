# Architecture — PlanningTree Rebuild

Version: 0.1.0-scaffold
Last updated: 2026-03-07

---

## Overview

PlanningTree is a local-first single-user desktop application distributed as an npm package. Users install and run it with `npx planningtree`. A single local process serves both the REST API and the React frontend from a dynamically chosen localhost port.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend language | Python 3.9+ | FastAPI + Uvicorn |
| HTTP framework | FastAPI | Schema validation via Pydantic |
| ASGI server | Uvicorn | Dev: `--reload`; prod: bundled via PyInstaller |
| AI (splits) | OpenAI Responses API | Direct API call; configurable model |
| AI (chat) | Codex app server subprocess | stdio JSON-RPC; per-node threads |
| Persistence | File-based JSON | No database |
| Real-time | Server-Sent Events (SSE) | Chat streaming only |
| Frontend | React 18 + TypeScript | Strict mode |
| Graph | @xyflow/react | Interactive task tree visualization |
| State management | Zustand | Replaces monolithic component state |
| Routing | React Router 6 | Graph Workspace ↔ Breadcrumb Workspace |
| Build tool | Vite 5 | Dev proxy → backend; prod static |
| CSS | CSS Modules + design tokens | Scoped per component; tokens.css for palette |
| Unit tests | Vitest (frontend), pytest (backend) | — |
| E2E tests | Playwright | Full app browser testing |
| Distribution | PyInstaller binary via npm | npx downloads platform binary |

---

## Top-Level Structure

```
PlanningTreeMain/
├── backend/          Python FastAPI app
├── frontend/         React SPA
├── launcher/         Node.js npx entry point (thin wrapper only)
├── scripts/          Dev, test, build scripts
└── docs/             Canonical rebuild specs and audit outputs
```

---

## Dependency Flow

```
[Browser]
    │ HTTP/SSE
    ▼
[frontend/] ──(dev: Vite proxy)──► [backend/]
                                        │
                          ┌─────────────┼──────────────┐
                          ▼             ▼               ▼
                    [filesystem]   [OpenAI API]   [Codex subprocess]
                    state.json     (splits)        (chat)
                    meta.json
                    chat_state.json
```

**Rules:**
- Frontend never touches the filesystem directly
- Backend services never call the OpenAI API directly — only through `ai/openai_client.py`
- Backend services never spawn subprocesses directly — only through `ai/codex_client.py`
- Routes never contain business logic — delegate to services

---

## Backend Layer Model

```
routes/         ← HTTP layer: parse request, call service, return response
  │
services/       ← Business logic: node CRUD, tree rules, split orchestration, chat
  │
storage/        ← Persistence: read/write JSON files atomically
ai/             ← AI integration: OpenAI API wrapper, Codex subprocess client
errors/         ← Typed error classes
config/         ← App config, env var resolution, platform-aware paths
```

### Layer Rules

| Layer | Owns | Must NOT |
|---|---|---|
| `routes/` | HTTP parsing, response shaping, error mapping to HTTP status | Contain business logic |
| `services/` | Business rules, domain invariants, orchestration | Touch filesystem directly, call external services directly |
| `storage/` | File I/O, atomic writes, schema reading/writing | Contain business logic |
| `ai/` | Subprocess management, API calls, prompt building | Contain business logic or HTTP concerns |
| `errors/` | Error type definitions | Contain logic |

---

## Frontend Layer Model

```
App.tsx          ← Router + layout only
  │
features/        ← Feature-scoped components (graph, breadcrumb, project, auth, node)
  │
stores/          ← Zustand state (project-store, ui-store, chat-store)
  │
api/             ← Typed HTTP client + React hooks
  │
components/      ← Shared stateless components (Layout, ErrorBoundary)
styles/          ← Design tokens and base styles only
```

### Frontend Rules

| Layer | Owns | Must NOT |
|---|---|---|
| `features/` | UI for a specific workspace or surface | Import from other feature directories |
| `stores/` | Client state, API call coordination | Contain rendering logic |
| `api/` | fetch wrapper, endpoint definitions | Contain business logic |
| `components/` | Shared stateless UI primitives | Contain state or API calls |

---

## Data Flow — User Actions

### Create + Split a Node

```
User clicks "Slice" button
  → GraphControls.tsx dispatches split action
  → project-store.splitNode(nodeId, "slice")
  → api/client.ts POST /v1/projects/{id}/nodes/{id}/split
  → routes/nodes.py validates request
  → services/split_service.py builds context + prompt
  → ai/openai_client.py calls OpenAI Responses API
  → split_service creates child nodes via node_service
  → storage/project_store.py writes updated state.json
  → route returns updated snapshot
  → project-store updates local state
  → TreeGraph re-renders with new children
```

### Finish Task → Mark Done

```
User clicks "Finish Task" on leaf node
  → client-side only (no API call)
  → ui-store.setActiveView("breadcrumb", nodeId)
  → React Router navigates to /node/:nodeId/chat
  → BreadcrumbWorkspace loads chat session
  → chat-store.loadSession(nodeId)
  → api GET /chat/session → returns session with composer draft
  → Draft pre-seeded from node title + description (by backend on first load)
  → User edits draft and sends → POST /chat/messages
  → SSE streams assistant response
  → User clicks "Mark Done"
  → api POST /nodes/{id}/complete
  → services/node_service.complete_node → sets status=done, unlocks next sibling
  → project-store refreshes snapshot
  → Graph updates to show done status
```

---

## Configuration

All configuration is via environment variables. No `.env` file is read at runtime (security boundary for `OPENAI_API_KEY`). Local preferences are stored in `config/app.json`.

| Env Var | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for split operations |
| `PLANNINGTREE_DATA_ROOT` | Platform default | Override app data directory |
| `PLANNINGTREE_PORT` | `8000` | Backend port (launcher finds free port) |
| `PLANNINGTREE_SPLIT_MODEL` | `gpt-4o` | OpenAI model for split generation |
| `PLANNINGTREE_SPLIT_TIMEOUT_SEC` | `120` | Timeout for split API call |
| `PLANNINGTREE_CODEX_CMD` | auto-discovered | Path to Codex binary for chat |

---

## Persistence

```
<app-data-root>/
├── config/
│   ├── app.json          # workspace root, preferences
│   └── auth.json         # session state, entitlement
└── projects/
    └── <project-id>/
        ├── meta.json     # project metadata
        ├── state.json    # live tree snapshot (schema_version: 2)
        └── chat_state.json  # per-node chat sessions
```

Platform defaults:
- Windows: `%APPDATA%\PlanningTree`
- macOS: `~/Library/Application Support/PlanningTree`
- Linux: `~/.local/share/PlanningTree`

---

## Auth Model

Cloud layer (thin): identity verification, entitlement check, token issuance.
Local layer: session persistence in `config/auth.json`, app shell auth check on boot.

In Phase 2-5 scaffold: always-authenticated stub (no real cloud auth).
In Phase 6: OAuth2 browser redirect flow integrated.

---

## Distribution (Phase 6 Target)

```
npm publish planningtree
  → package.json bin → launcher/cli.js
  → cli.js detects platform
  → postinstall downloads platform binary from GitHub Releases
  → binary = PyInstaller-bundled Python backend + static frontend dist
  → cli.js spawns binary, finds free port, opens browser
```
