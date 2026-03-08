# Hotspots and Technical Debt — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

---

## File Size Hotspots

These files are critically oversized and are primary sources of technical debt.

| File | Lines | Problem |
|---|---|---|
| `backend/orchestrator.py` | ~2,800 | God object: node CRUD, split, planning, gate execution, versioning, rollback, locking — all in one class |
| `frontend/src/app/App.tsx` | ~1,554 | All state, all event handlers, all API calls, all SSE management in one component |
| `frontend/src/features/graph/WorkflowGraph.tsx` | ~1,554 | Graph rendering, action menus, node layout, collapse logic, event handling, fullscreen — monolithic |
| `frontend/src/styles.css` | ~2,591 | All styles for the entire app in one flat file; no scoping; 5 theme variants inline |
| `backend/storage.py` | ~1,200 | File I/O, audit writing, version management, checkpoint management, migration logic all mixed |
| `backend/worker_adapter.py` | ~800 | Builds Codex invocation configs for split, plan, gate — mixed concerns; gate config is 50%+ of this file |

---

## Architectural Hotspots

### 1. Orchestrator God Object (`backend/orchestrator.py`)

**Problem:** The `Orchestrator` class is responsible for:
- Node CRUD (create, update, finish, close)
- AI split orchestration (walking_skeleton, slice)
- Gate planning and execution
- Rollback and checkpoint management
- Version creation and restoration
- Project management
- Locking coordination

This violates single responsibility at scale. Adding or removing any feature requires understanding the entire file. Gate removal alone requires surgically extracting ~40% of the file.

**Evidence:** The gate system's removal is complicated precisely because gate logic (`run_gate`, `plan_gates`, `rollback`) is interleaved with core node logic (`create_node`, `finish_node`) using shared state (`current_gate_id`, `gate_plan`).

**Rebuild fix:** Split into: `project_service.py`, `node_service.py`, `tree_service.py`, `split_service.py`, `chat_service.py`.

---

### 2. Storage Layer Doing Too Much (`backend/storage.py`)

**Problem:** Storage handles:
- JSON read/write for project state
- Append-only audit event writing (26 event types)
- Version snapshot creation and restoration
- Checkpoint creation and management
- Schema migrations
- File locking utilities
- Gate run archive management

Audit writing is embedded in every mutation method. Removing audit requires finding and stripping calls throughout the file.

**Rebuild fix:** Storage module handles only file I/O. Audit removed. Simplified to: project CRUD (state.json), chat state CRUD (chat_state.json), app config CRUD (app.json, auth.json).

---

### 3. Monolithic React Component (`frontend/src/app/App.tsx`)

**Problem:** 1,554 lines of:
- Project list state + fetching
- Snapshot state + fetching
- SSE connection management
- Theme management
- Version list state + fetching
- Preview mode state
- All API call handlers (`handleSplitNode`, `handleFinishTask`, `handleRollback`, `handleRunGate`, etc.)
- UI flag state (~15 boolean flags)
- Render logic for control rack, topbar, and panel layout

No separation between state management, side effects, and rendering.

**Rebuild fix:** Zustand stores for state (project-store, ui-store, chat-store). Feature components own their own state interactions. App.tsx becomes router + layout only.

---

### 4. LangGraph Complexity for Split (`backend/split_graph.py`)

**Problem:** The split operation uses a full LangGraph state graph with:
- Multiple graph nodes: generate → parse → normalize → drift evaluation → conditional retry
- SqliteSaver checkpointer for graph state persistence
- Up to 3 retry attempts with exponential backoff
- Drift evaluation comparing initial context vs. final split output

This is significant complexity for what is essentially: build prompt → call AI → parse response → create nodes.

The drift evaluation was added to handle cases where the AI output didn't align with the input context, but it adds ~200 lines of code and a SQLite dependency for minimal observed benefit.

**Rebuild fix:** Direct function call to OpenAI Responses API. Simple retry wrapper (max 2 retries on parse failure). No LangGraph. No checkpointer.

---

### 5. WorkflowGraph Size (`frontend/src/features/graph/WorkflowGraph.tsx`)

**Problem:** 1,554 lines covering:
- ReactFlow graph initialization and configuration
- Custom node card rendering with status logic
- Collapse/expand tree management
- Node action menu rendering (split, finish, plan gates, run gate)
- Breadcrumb trigger integration
- Fullscreen mode
- Graph layout algorithm
- Event handlers for all node interactions

Single file mixes concerns: layout algorithm, rendering, interaction, and feature logic.

**Rebuild fix:** Decompose into GraphWorkspace.tsx (coordinator), TreeGraph.tsx (@xyflow/react wiring), GraphNode.tsx + GraphNode.module.css (node card), GraphControls.tsx (action buttons). Remove gate-era actions.

---

### 6. Global CSS (`frontend/src/styles.css`)

**Problem:** 2,591 lines of global CSS with:
- 5 complete theme variants inlined (warm-earth, slate, forest, obsidian, amethyst)
- No CSS scoping — class name collisions possible
- Deep nesting without BEM or module conventions
- Mixed concerns: layout, components, utilities, animations all in one file
- Difficult to know which rules are still in use

**Rebuild fix:** CSS Modules per component for scoped styles. `styles/tokens.css` for design tokens (custom properties). `styles/globals.css` for base resets and typography only.

---

### 7. Dead Code and Unused Patterns

| Location | Issue |
|---|---|
| `frontend/src/components/` | Directory exists but is empty |
| `frontend/src/pages/` | Directory exists but is empty |
| Gate config in `worker_adapter.py` | Entire gate config section will be dead code post-removal |
| `backend/envelope.py` + `envelope_handlers.py` | Gate output validation — fully removed |
| `backend/fsm.py` | FSM states `planned`, `running`, `blocked` become dead after status model change |
| Version endpoints in `routers/projects.py` | Dead post version removal |
| VersionNavigator, ReconfirmationPanel, ContextLens | Dead UI components post removal |

---

### 8. Missing Auth and Security

**Problem:** No authentication or authorization. CORS is open (`allow_origins=["*"]`). All endpoints are unprotected. This is intentional for the prototype but is a hard gap for any distribution.

**Rebuild fix:** Cloud auth (identity + license) before distribution. Until Phase 6, stub auth with always-authenticated local session.

---

### 9. No Config File Support

**Problem:** All configuration is via environment variables only. No `.env` file support, no `env.example`, no first-run config flow. New developers must manually discover and set required env vars.

**Rebuild fix:** `config/app.json` for runtime config. First-run UI flow for workspace setup. `OPENAI_API_KEY` remains an env var (secret, should not be in config files).

---

### 10. No CI Pipeline

**Problem:** No automated tests on push, no build verification, no lint checks. Tests run manually only.

**Rebuild fix:** GitHub Actions (at minimum): lint + unit tests on push; E2E on PR. PyInstaller build matrix (Windows/macOS/Linux) on release tag.

---

## Summary Table

| Hotspot | Severity | Rebuild Action |
|---|---|---|
| orchestrator.py (2,800 lines) | Critical | Decompose into 5 services |
| App.tsx (1,554 lines) | Critical | Decompose into stores + feature components |
| WorkflowGraph.tsx (1,554 lines) | High | Decompose into 4 components |
| styles.css (2,591 lines) | High | CSS Modules + tokens file |
| storage.py (1,200 lines) | High | Simplify (remove audit/versions/checkpoints) |
| LangGraph split complexity | High | Replace with direct OpenAI API call |
| No auth | Critical (for dist) | Cloud auth in Phase 6 |
| No CI | High | GitHub Actions setup in scaffold phase |
| Dead UI components | Low | Delete (VersionNavigator, ContextLens, ReconfirmationPanel) |
| No config file support | Medium | app.json + first-run flow |
