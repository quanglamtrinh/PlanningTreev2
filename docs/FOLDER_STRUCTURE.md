# Folder Structure — PlanningTree Rebuild

Version: 0.1.0-scaffold
Last updated: 2026-03-07

---

## Ownership Rules

- Each directory has a single clear owner (a layer or feature)
- No directory serves as a "utils dumping ground"
- Cross-feature imports in `frontend/src/features/` are forbidden
- Business logic lives in `backend/services/` only — never in routes or storage

---

## Full Structure

```
PlanningTreeMain/
│
├── package.json                  # Root npm package (npx entry, dev scripts)
├── pyproject.toml                # Python project metadata, ruff config, pytest config
├── .gitignore
├── .env.example                  # Required env vars with descriptions
│
├── launcher/                     # Node.js npx entry point
│   ├── cli.js                    # Parse args, spawn backend binary, open browser
│   └── platform.js               # Resolve platform-specific binary path
│
├── backend/                      # Python FastAPI application
│   ├── __init__.py
│   ├── main.py                   # App factory: create_app() → FastAPI
│   │
│   ├── config/                   # Configuration and env var resolution
│   │   ├── __init__.py
│   │   └── app_config.py         # Data root paths, timeouts, model names
│   │
│   ├── storage/                  # File I/O — the only layer touching disk
│   │   ├── __init__.py
│   │   ├── storage.py            # Main storage class (facade)
│   │   ├── project_store.py      # Read/write meta.json and state.json
│   │   ├── chat_store.py         # Read/write chat_state.json
│   │   ├── config_store.py       # Read/write app.json and auth.json
│   │   └── file_utils.py         # Atomic write, ensure_dir, safe JSON load
│   │
│   ├── services/                 # Business logic — no I/O, no HTTP, no AI calls
│   │   ├── __init__.py
│   │   ├── project_service.py    # Create project, list projects, get snapshot
│   │   ├── node_service.py       # Create node, update, status transitions, complete
│   │   ├── tree_service.py       # Tree validation, sibling unlock, ancestry
│   │   ├── split_service.py      # Split orchestration (calls ai/openai_client)
│   │   ├── chat_service.py       # Chat sessions, message handling, draft seeding
│   │   └── auth_service.py       # Local session, entitlement check stub
│   │
│   ├── ai/                       # AI integration — all subprocess and API calls
│   │   ├── __init__.py
│   │   ├── openai_client.py      # OpenAI Responses API wrapper (splits)
│   │   ├── codex_client.py       # Codex app server subprocess (chat threads)
│   │   ├── split_prompt_builder.py  # Prompt construction for ws/slice modes
│   │   └── context_builder.py    # Build ancestry context from tree snapshot
│   │
│   ├── routes/                   # HTTP handlers — thin, validate + delegate only
│   │   ├── __init__.py
│   │   ├── bootstrap.py          # GET /v1/bootstrap/status
│   │   ├── auth.py               # Auth session routes
│   │   ├── settings.py           # GET/PATCH /v1/settings/workspace
│   │   ├── projects.py           # Project CRUD + snapshot
│   │   ├── nodes.py              # Node CRUD + split + complete
│   │   └── chat.py               # Chat session + messages + SSE events
│   │
│   ├── streaming/                # SSE event broker for chat
│   │   ├── __init__.py
│   │   ├── sse_broker.py         # Pub/sub for chat streaming events
│   │   └── event_types.py        # ChatEvent type definitions
│   │
│   ├── errors/                   # Typed error classes
│   │   ├── __init__.py
│   │   └── app_errors.py         # AppError base + all typed errors
│   │
│   └── tests/                    # Backend tests
│       ├── __init__.py
│       ├── unit/                 # Unit tests per service/storage module
│       │   └── __init__.py
│       └── integration/          # Route-level tests using httpx TestClient
│           └── __init__.py
│
├── frontend/                     # React SPA
│   ├── package.json
│   ├── tsconfig.json             # References app + node tsconfigs
│   ├── tsconfig.app.json         # Source compilation config
│   ├── tsconfig.node.json        # Build tool config
│   ├── vite.config.ts            # Vite: dev proxy, build config
│   ├── vitest.config.ts          # Unit test runner config
│   ├── playwright.config.ts      # E2E test config
│   ├── index.html                # HTML entry point
│   │
│   └── src/
│       ├── main.tsx              # React root mount
│       ├── App.tsx               # Router + layout only (thin)
│       │
│       ├── api/                  # HTTP client — the only layer calling fetch()
│       │   ├── client.ts         # Typed fetch wrapper, base URL, error handling
│       │   └── hooks.ts          # React hooks for common API calls
│       │
│       ├── stores/               # Zustand state — all client state lives here
│       │   ├── project-store.ts  # Projects list, active snapshot, node mutations
│       │   ├── ui-store.ts       # Active view (graph/breadcrumb), selected node, theme
│       │   └── chat-store.ts     # Chat session, messages, streaming state, draft
│       │
│       ├── features/             # Feature-scoped UI surfaces
│       │   │
│       │   ├── auth/             # Login page + workspace setup
│       │   │   ├── LoginPage.tsx
│       │   │   └── WorkspaceSetup.tsx
│       │   │
│       │   ├── graph/            # Graph Workspace (primary planning surface)
│       │   │   ├── GraphWorkspace.tsx    # Layout coordinator
│       │   │   ├── TreeGraph.tsx         # @xyflow/react graph
│       │   │   ├── GraphNode.tsx         # Custom node card component
│       │   │   ├── GraphNode.module.css
│       │   │   └── GraphControls.tsx     # Split + Finish Task buttons
│       │   │
│       │   ├── breadcrumb/       # Breadcrumb Workspace (execution surface)
│       │   │   ├── BreadcrumbWorkspace.tsx  # Layout coordinator
│       │   │   ├── BreadcrumbHeader.tsx     # Ancestry trail (root → current)
│       │   │   ├── ChatPanel.tsx            # Chat thread + streaming + composer
│       │   │   ├── ChatPanel.module.css
│       │   │   └── MarkDoneButton.tsx
│       │   │
│       │   ├── project/          # Project list + create
│       │   │   ├── ProjectList.tsx
│       │   │   └── CreateProjectDialog.tsx
│       │   │
│       │   └── node/             # Node detail + editing
│       │       ├── NodeEditor.tsx          # Title + description editing
│       │       └── NodeStatusBadge.tsx     # Status chip
│       │
│       ├── components/           # Shared stateless UI primitives
│       │   ├── Layout.tsx        # App shell layout
│       │   └── ErrorBoundary.tsx # React error boundary
│       │
│       └── styles/               # Global design tokens and base styles only
│           ├── tokens.css        # CSS custom properties (colors, spacing, radius)
│           └── globals.css       # Base resets, body, typography
│
├── scripts/                      # Dev and build scripts
│   ├── dev.py                    # Start backend + frontend for local development
│   ├── build_backend.py          # PyInstaller build (produces platform binary)
│   └── package_release.py        # Assemble npm release package
│
└── docs/                         # Documentation
    ├── README.md                 # Canonical docs index
    ├── audit/                    # Phase 1 audit outputs
    │   ├── SYSTEM_OVERVIEW.md
    │   ├── FEATURE_INVENTORY.md
    │   ├── DEPENDENCY_MAP.md
    │   ├── DATA_AND_CONTRACTS.md
    │   ├── ENV_AND_DEPLOY.md
    │   ├── HOTSPOTS_AND_TECH_DEBT.md
    │   ├── REBUILD_CLASSIFICATION.md
    │   └── EXECUTIVE_SUMMARY.md
    ├── ARCHITECTURE.md           # This module's architecture doc
    ├── FOLDER_STRUCTURE.md       # This file
    ├── AGENT_RULES.md            # Rules for AI agents working in this codebase
    ├── TEST_STRATEGY.md          # Testing approach per layer
    ├── MIGRATION_PLAN.md         # Feature migration order and strategy
    └── features/                 # Per-feature migration specs (created in Phase 5)
```

---

## What Goes Where — Quick Reference

| What | Where |
|---|---|
| Database call / file read | `backend/storage/` only |
| Business rule / domain invariant | `backend/services/` only |
| OpenAI API call | `backend/ai/openai_client.py` only |
| Codex subprocess management | `backend/ai/codex_client.py` only |
| Split prompt template | `backend/ai/split_prompt_builder.py` only |
| HTTP request handling | `backend/routes/` only |
| SSE event publishing | `backend/streaming/sse_broker.py` only |
| fetch() call | `frontend/src/api/client.ts` only |
| React state | `frontend/src/stores/` only |
| Graph UI | `frontend/src/features/graph/` only |
| Chat UI | `frontend/src/features/breadcrumb/` only |
| Shared UI atoms | `frontend/src/components/` only |
| CSS tokens (colors, spacing) | `frontend/src/styles/tokens.css` only |
| Component-specific styles | `ComponentName.module.css` next to component |

---

## Anti-Patterns to Avoid

- No `utils.py` or `helpers.ts` dumping grounds
- No business logic in `routes/`
- No `fetch()` calls in React components (use `api/hooks.ts`)
- No cross-feature imports (`features/graph/` must not import from `features/breadcrumb/`)
- No gate, rollback, version, or audit concepts anywhere
- No `styles.css` global stylesheet (use CSS Modules per component)
