# Rebuild Classification — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

Classification per module, file, and concept. Every item explicitly classified as one of:
- **KEEP** — port with minimal changes
- **SIMPLIFY** — port core logic, remove complexity
- **REWRITE** — same purpose, new implementation
- **REMOVE** — no equivalent in rebuild
- **NEW** — no legacy equivalent; built from scratch

---

## Backend — Python

### Core Infrastructure

| File / Module | Classification | Reason |
|---|---|---|
| `backend/main.py` | REWRITE | Simplified: remove gate/audit/version initialization; cleaner app factory |
| `backend/config/app_config.py` | NEW | No equivalent; env vars + app.json config management |
| `backend/config/auth_config.py` | NEW | No equivalent; auth session config |

### Storage

| File / Module | Classification | Reason |
|---|---|---|
| `backend/storage.py` | REWRITE | Keep file I/O patterns + atomic write approach; remove audit, versions, checkpoints, gate archives; simplify to 3 files (meta, state, chat_state) |
| Atomic write pattern | KEEP | Write to `.tmp` → rename — correct approach, port directly |
| Platform-aware data root | KEEP | Windows/macOS/Linux path logic — useful pattern |
| Schema migration logic | SIMPLIFY | Keep migration framework, drop all v1 migrations |
| Audit append logic | REMOVE | audit.ndjson removed entirely |
| Version management | REMOVE | versions/ directory and all related code |
| Checkpoint management | REMOVE | checkpoints/ directory and all related code |
| Gate run archive | REMOVE | gate_runs_archive.ndjson removed |

### Services (Decomposed from Orchestrator)

| Legacy Source | New Module | Classification |
|---|---|---|
| `orchestrator.py` create_project, list_projects | `services/project_service.py` | SIMPLIFY |
| `orchestrator.py` create_node, update_node | `services/node_service.py` | SIMPLIFY |
| `orchestrator.py` status transitions + FSM | `services/node_service.py` | REWRITE (new status model) |
| `orchestrator.py` sibling unlock | `services/tree_service.py` | NEW (no equivalent in legacy) |
| `orchestrator.py` finish_node, close_node | Removed from backend | REMOVE (Finish Task is client-side; Mark Done via complete endpoint) |
| `orchestrator.py` plan_gates, run_gate | REMOVE | Gate system removed |
| `orchestrator.py` rollback | REMOVE | Rollback removed |
| `orchestrator.py` list_versions, restore_version | REMOVE | Version restore removed |
| `chat_service.py` | `services/chat_service.py` | SIMPLIFY (remove gate context from sessions) |
| `lock_manager.py` | REMOVE | File-based project lock removed (single-user local app; no concurrent mutations) |

### AI Integration

| File / Module | Classification | Reason |
|---|---|---|
| `codex_app_client.py` | SIMPLIFY | Port subprocess JSON-RPC pattern to new `ai/codex_client.py`; clean up error handling and buffering; keep for chat |
| `split_planner.py` | SIMPLIFY | Port prompt templates and context building; remove gate/scope fence references; adapt to title/description model |
| `context_projection.py` | SIMPLIFY | Port ancestry chain construction; remove gate context projection |
| `worker_adapter.py` | REWRITE → REMOVE (partial) | Split config for chat stays (simplified); gate config removed; new `ai/openai_client.py` for split |
| `split_graph.py` | REMOVE | LangGraph state graph removed; direct OpenAI API call replaces it |
| `envelope.py` | REMOVE | Gate output validation removed |
| `envelope_handlers.py` | REMOVE | Gate output handler types removed |
| `langgraph_runner.py` | REMOVE | LangGraph execution wrapper removed |

### Routes

| File / Module | Classification | Reason |
|---|---|---|
| `routers/projects.py` (create, list, snapshot) | KEEP | Port to new route structure; slim down |
| `routers/projects.py` (versions, rollback, reset) | REMOVE | Version and rollback routes removed |
| `routers/projects.py` (nodes: split, finish, close) | REWRITE | New split contract; finish removed; close → complete |
| `routers/chat.py` | SIMPLIFY | Keep session/message/SSE; remove gate context from config |
| `routers/events.py` | REMOVE | Project-wide audit SSE removed |
| `routers/metrics.py` | REMOVE | Metrics endpoint removed |
| New: `routers/bootstrap.py` | NEW | Bootstrap status endpoint |
| New: `routers/auth.py` | NEW | Auth session routes |
| New: `routers/settings.py` | NEW | Workspace settings routes |

### FSM and Domain Model

| File / Module | Classification | Reason |
|---|---|---|
| `fsm.py` | REWRITE | New status model: locked/draft/ready/in_progress/done. Drop planned/running/blocked/closed. |

---

## Frontend — React/TypeScript

### Core

| File | Classification | Reason |
|---|---|---|
| `src/main.tsx` | KEEP | Minimal entry point, no logic |
| `src/app/App.tsx` | REWRITE | Decompose into stores + React Router + thin layout; remove SSE audit management, preview mode, version UI |
| `src/app/ErrorBoundary.tsx` | KEEP | Straightforward, reuse as-is |

### State Management

| File | Classification | Reason |
|---|---|---|
| `src/store.ts` | REMOVE | Audit event store; entirely removed |
| `src/selection.ts` | SIMPLIFY | Node selection logic; port core behavior |
| Zustand stores (new) | NEW | project-store, ui-store, chat-store replace App.tsx state |

### API and Networking

| File | Classification | Reason |
|---|---|---|
| `src/client.ts` | REWRITE | Port fetch wrapper pattern; update endpoints to new API surface; remove gate/rollback/version/metrics calls |
| `src/sseManager.ts` | SIMPLIFY | Keep SSE + reconnect + backoff pattern; remove audit event tracking (`lastSeq`); used for chat SSE only |
| `src/contracts.ts` | REWRITE | New types: title/description model, new status enum, remove gate/audit/version types |

### Features — Graph

| File | Classification | Reason |
|---|---|---|
| `features/graph/WorkflowGraph.tsx` | REWRITE | Decompose into GraphWorkspace, TreeGraph, GraphNode, GraphControls; migrate to @xyflow/react; remove gate actions |

### Features — Breadcrumb / Chat

| File | Classification | Reason |
|---|---|---|
| `features/breadcrumb/BreadcrumbView.tsx` | REWRITE | Becomes BreadcrumbWorkspace (full page, not sidebar); add Mark Done button |
| `features/breadcrumb/ChatPanel.tsx` | SIMPLIFY | Keep streaming UI, message display, composer; remove chat config editing complexity |

### Features — Node Detail

| File | Classification | Reason |
|---|---|---|
| `features/node-detail/NodeDetailPanel.tsx` | REWRITE | Remove gate buttons, version info; simplify to node editor (title + description); inline with graph node |

### Features — Removed

| File | Classification | Reason |
|---|---|---|
| `features/version-navigator/VersionNavigator.tsx` | REMOVE | Version history removed |
| `features/reconfirmation/ReconfirmationPanel.tsx` | REMOVE | Gate reconfirmation removed |
| `features/context-lens/ContextLens.tsx` | REMOVE | Metadata dashboard removed |

### Styles

| File | Classification | Reason |
|---|---|---|
| `src/styles.css` | REWRITE | Extract design tokens to `styles/tokens.css`; extract base styles to `styles/globals.css`; component styles move to CSS Modules; 5 themes kept |

---

## Concepts and Patterns

| Legacy Concept | Classification | Rebuild Equivalent |
|---|---|---|
| `prompt` field | REPLACE | `description` |
| `short_title` field | REPLACE | `title` |
| `finish_node` API | REMOVE | Client-side Finish Task action |
| `close_node` API | REPLACE | `POST /complete` (Mark Done) |
| `planned` status | REPLACE | `ready` |
| `running` status | REPLACE | `in_progress` |
| `closed` status | REPLACE | `done` |
| `blocked` status | REMOVE | No equivalent |
| Gate plan | REMOVE | — |
| Gate run | REMOVE | — |
| Rollback checkpoint | REMOVE | — |
| Version snapshot | REMOVE | — |
| Audit event (26 types) | REMOVE | — |
| Audit SSE stream | REMOVE | — |
| Reconfirmation | REMOVE | — |
| ContextLens | REMOVE | — |
| Preview mode | REMOVE | — |
| LangGraph split graph | REMOVE | Direct OpenAI API call |
| LangGraph SqliteSaver | REMOVE | — |
| File-based lock | REMOVE | Single-user local app; no concurrent mutations needed |
| Codex subprocess (for splits) | REPLACE | OpenAI Responses API |
| Codex subprocess (for chat) | KEEP | Codex app server threads |
| Workspace root (env var only) | REPLACE | Stored in app.json + first-run UI selection |

---

## Summary Counts

| Classification | Count |
|---|---|
| KEEP | 8 |
| SIMPLIFY | 14 |
| REWRITE | 11 |
| REMOVE | 28 |
| NEW | 8 |
