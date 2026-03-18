# Architecture - PlanningTree Rebuild

Version: 0.2.0-phase-c
Last updated: 2026-03-17

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
| Persistence | File-based JSON + Markdown + YAML | `tree.json` plus per-node document files |
| Real-time | Server-Sent Events (SSE) | Chat streaming only |
| Frontend | React 18 + TypeScript | Strict mode |
| Graph | @xyflow/react | Interactive task tree visualization |
| State management | Zustand | Replaces monolithic component state |
| Routing | React Router 6 | Graph Workspace <-> Breadcrumb Workspace |
| Build tool | Vite 5 | Dev proxy -> backend; prod static |
| CSS | CSS Modules + design tokens | Scoped per component; tokens.css for palette |
| Unit tests | Vitest (frontend), pytest (backend) | - |
| E2E tests | Playwright | Full app browser testing |
| Distribution | PyInstaller binary via npm | npx downloads platform binary |

---

## Top-Level Structure

```text
PlanningTreeMain/
|- backend/          Python FastAPI app
|- frontend/         React SPA
|- launcher/         Node.js npx entry point (thin wrapper only)
|- scripts/          Dev, test, build scripts
`- docs/             Canonical rebuild specs and audit outputs
```

---

## Dependency Flow

```text
[Browser]
    | HTTP/SSE
    v
[frontend/] --(dev: Vite proxy)--> [backend/]
                                     |
                   +-----------------+------------------+
                   v                 v                  v
             [filesystem]      [OpenAI API]     [Codex subprocess]
             tree.json         (splits)         (chat)
             nodes/*/*.md
             nodes/*/state.yaml
             thread_state.json
             chat_state.json
```

**Rules:**
- Frontend never touches the filesystem directly
- Backend services never call the OpenAI API directly - only through `ai/openai_client.py`
- Backend services never spawn subprocesses directly - only through `ai/codex_client.py`
- Routes never contain business logic - delegate to services

---

## Backend Layer Model

```text
routes/         <- HTTP layer: parse request, call service, return response
  |
services/       <- Business logic: node CRUD, tree rules, split orchestration, chat
  |
storage/        <- Persistence: read/write JSON, Markdown, and YAML files atomically
ai/             <- AI integration: OpenAI API wrapper, Codex subprocess client
errors/         <- Typed error classes
config/         <- App config, env var resolution, platform-aware paths
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

```text
App.tsx          <- Router + layout only
  |
features/        <- Feature-scoped components (graph, breadcrumb, project, auth, node)
  |
stores/          <- Zustand state (project-store, ui-store, chat-store)
  |
api/             <- Typed HTTP client + React hooks
  |
components/      <- Shared stateless components (Layout, ErrorBoundary)
styles/          <- Design tokens and base styles only
```

### Frontend Rules

| Layer | Owns | Must NOT |
|---|---|---|
| `features/` | UI for a specific workspace or surface | Import from other feature directories |
| `stores/` | Client state, API call coordination | Contain rendering logic |
| `api/` | fetch wrapper, endpoint definitions | Contain business logic |
| `components/` | Shared stateless UI primitives | Contain state or API calls |

---

## Data Flow - User Actions

### Create + Split a Node

```text
User opens the GraphNode action menu and chooses a split mode
  -> TreeGraph forwards onSplitNode(nodeId, mode)
  -> GraphWorkspace prompts for replace confirmation when active children already exist
  -> project-store.splitNode(nodeId, mode, confirmReplace)
  -> api/client.ts POST /v1/projects/{id}/nodes/{id}/split
  -> routes/split.py validates the canonical mode and confirm_replace flag
  -> services/split_service.py starts the planning turn and returns 202 accepted
  -> split_service builds context, runs the planning turn, and materializes child nodes on completion
  -> storage/project_store.py writes updated tree.json
  -> storage/node_store.py writes task.md / briefing.md / spec.md / state.yaml
  -> planning events plus snapshot/history refresh update client state
  -> TreeGraph re-renders with the new children
```

### Finish Task -> Mark Done

```text
User clicks "Finish Task" on leaf node
  -> client-side only (no API call)
  -> React Router navigates to /projects/:projectId/nodes/:nodeId/chat
  -> BreadcrumbWorkspace loads chat session
  -> chat-store.loadSession(projectId, nodeId)
  -> GraphWorkspace passes a transient router-state seed built from node title + description
  -> BreadcrumbWorkspace applies that seed into the local composer once
  -> User edits draft and sends -> POST /chat/messages
  -> First accepted message promotes ready -> in_progress
  -> SSE streams assistant response
  -> User clicks "Mark Done"
  -> api POST /nodes/{id}/complete
  -> services/node_service.complete_node -> sets status=done, unlocks next sibling
  -> project-store refreshes snapshot
  -> Graph updates to show done status
```

---

## Configuration

All configuration is via environment variables. No `.env` file is read at runtime (security boundary for `OPENAI_API_KEY`). Local preferences are stored in `config/app.json`.

| Env Var | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | - | Required for split operations |
| `PLANNINGTREE_DATA_ROOT` | Platform default | Override app data directory |
| `PLANNINGTREE_PORT` | `8000` | Backend port (launcher finds free port) |
| `PLANNINGTREE_SPLIT_MODEL` | `gpt-4o` | OpenAI model for split generation |
| `PLANNINGTREE_SPLIT_TIMEOUT_SEC` | `120` | Timeout for split API call |
| `PLANNINGTREE_CODEX_CMD` | auto-discovered | Path to Codex binary for chat |

---

## Persistence

```text
<app-data-root>/
|- config/
|  |- app.json          # workspace root, preferences
|  `- auth.json         # session state, entitlement
`- projects/
   `- <project-id>/
      |- meta.json         # project metadata
      |- tree.json         # live tree index (schema_version: 5)
      |- chat_state.json   # per-node chat sessions
      |- thread_state.json # planning / execution / ask thread state
      `- nodes/
         `- <node-id>/
            |- task.md
            |- briefing.md
            |- spec.md
            `- state.yaml
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

```text
npm publish planningtree
  -> package.json bin -> launcher/cli.js
  -> cli.js detects platform
  -> postinstall downloads platform binary from GitHub Releases
  -> binary = PyInstaller-bundled Python backend + static frontend dist
  -> cli.js spawns binary, finds free port, opens browser
```
