# Feature Inventory — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

Each feature lists current behavior and rebuild disposition. Disposition codes: **KEEP**, **REWRITE**, **SIMPLIFY**, **REMOVE**.

---

## F1: Project Management

**Disposition: KEEP / SIMPLIFY**

**Current behavior:**
- Users create named projects via the UI
- Projects are isolated workspaces with their own tree, chat sessions, and version history
- Project list shown in a dropdown at the top of the page
- Each project has a `meta.json` (name, id, created_at, workspace_root) and `state.json` (current tree snapshot)

**Backend:** `routers/projects.py` → `Orchestrator.create_project()`, `Orchestrator.list_projects()`

**Frontend:** Project selector dropdown in `App.tsx`; create project button

**Changes in rebuild:**
- Remove version history from project model
- Remove audit trail from project model
- Project workspace root selection becomes part of first-run flow
- Rename `prompt` field → `description`; rename `short_title` → `title`

---

## F2: Tree Visualization (Graph)

**Disposition: REWRITE**

**Current behavior:**
- Interactive ReactFlow graph shows the task tree
- Nodes rendered as custom cards with status colors, collapse/expand, and action menus
- Action menus on each node: Split (Walking Skeleton, Slice), Finish Task, Plan Gates, Run Gate
- Breadcrumb navigation button per node
- Fullscreen mode
- Graph updates when SSE events arrive (snapshot refresh)

**Frontend:** `features/graph/WorkflowGraph.tsx` (~1,554 lines, critical hotspot)

**Changes in rebuild:**
- Remove gate-related actions (Plan Gates, Run Gate) from node menus
- Remove version preview overlay
- Migrate to `@xyflow/react` (successor library)
- Break into smaller components (GraphNode, GraphControls, GraphLayout)
- Replace SSE-driven refresh with direct API response updates

---

## F3: Node CRUD

**Disposition: KEEP / SIMPLIFY**

**Current behavior:**
- Create root node automatically on project creation
- Create child nodes explicitly
- Edit node `prompt` (goal text) via textarea in `NodeDetailPanel`
- Node has: id, short_title, prompt, status, parent_id, child_ids, planning_mode, transition, gate_plan
- Status lifecycle: locked → draft → planned → running → blocked → closed

**Backend:** `Orchestrator.create_node()`, `Orchestrator.update_node_prompt()`

**Changes in rebuild:**
- Rename `prompt` → `description`, `short_title` → `title`
- Simplify status model: locked → draft → ready → in_progress → done
- Remove `gate_plan`, `transition` fields from public model
- Remove `planned`, `running`, `blocked` statuses

---

## F4: AI Split — Walking Skeleton

**Disposition: KEEP / REWRITE**

**Current behavior:**
- User clicks "Walking Skeleton" button on a node
- Backend calls Codex app server with a structured prompt built by `split_planner.py`
- Codex generates a phased plan (thin end-to-end slices: e.g., skeleton → data → logic → polish)
- Response parsed as JSON, normalized into child nodes
- LangGraph state graph handles: generate → parse → normalize → drift eval → retry (up to 3)
- New child nodes created with status `draft` and `planning_mode = "walking_skeleton"`
- Parent node status transitions to `planned`

**Backend:** `split_graph.py`, `split_planner.py`, `worker_adapter.py`, `langgraph_runner.py`, `context_projection.py`

**Frontend:** "Walking Skeleton" button in `NodeDetailPanel` and `WorkflowGraph` action menu

**Changes in rebuild:**
- Remove LangGraph drift-retry complexity (direct OpenAI API call)
- Replace Codex subprocess for splits → OpenAI Responses API
- Adapt prompts from `prompt/goal_parse` model → `title/description` model
- Remove scope fence and gate context from prompt
- New children: first child `ready`, rest `locked` (previously first child `draft`)

---

## F5: AI Split — Slice

**Disposition: KEEP / REWRITE**

**Current behavior:**
- Same flow as Walking Skeleton but generates ordered subtask decomposition
- Prompt template focuses on vertical feature slices (each slice is independently deliverable)
- Generates 3-7 child nodes by default

**Backend:** Same modules as F4 but with `split_mode = "slice"` in prompt builder

**Frontend:** "Slice" button in `NodeDetailPanel` and `WorkflowGraph` action menu

**Changes in rebuild:** Same as F4.

---

## F6: Finish Task (Legacy)

**Disposition: REMOVE / REPLACE**

**Current behavior:**
- "Finish Task" button in `NodeDetailPanel` calls `POST /v1/projects/{id}/nodes/{id}/finish`
- Backend marks node as `closed` and creates a new version snapshot
- Requires node to have no active children

**Backend:** `Orchestrator.finish_node()`

**Frontend:** `NodeDetailPanel.tsx` → `onFinishTask()` → `api.finishNode()`

**Changes in rebuild:**
- Finish Task becomes a **client-side UX action** — no backend endpoint
- Action: save pending edits → navigate to Breadcrumb Workspace → seed composer with prefilled draft (title + description)
- Actual completion happens via explicit **Mark Done** (separate action)

---

## F7: Gate Workflow

**Disposition: REMOVE**

**Current behavior:**
- After planning a node, user can request a "gate plan" — a set of checkpoints/verification steps
- `POST /v1/projects/{id}/nodes/{id}/plan-gates` — generates gate plan via Codex
- `POST /v1/projects/{id}/nodes/{id}/gates/{gateId}/run` — executes a gate
- Gates run in sequence; a gate can PASS, FAIL, BLOCK, or request user input
- Gate results stored in `gate_runs_archive.ndjson` and `artifacts/`
- Rollback available when `current_gate_id` is set

**Backend:** `Orchestrator.plan_gates()`, `Orchestrator.run_gate()`, `envelope.py`, `envelope_handlers.py`, `worker_adapter.py` (gate config)

**Frontend:** "Plan Gates" button, "Run Gate" button, gate status display in `NodeDetailPanel`

**Rebuild:** Entire gate system removed from v1. No replacement.

---

## F8: Rollback

**Disposition: REMOVE**

**Current behavior:**
- Available when a gate run has set a `current_gate_id`
- `POST /v1/projects/{id}/actions/rollback` — restores state to the snapshot captured before the current gate ran
- Checkpoints stored in `checkpoints/state/` and `checkpoints/runtime/`
- Rollback button in UI control rack, disabled unless rollback is available

**Backend:** `Orchestrator.rollback()`, checkpoint management in `storage.py`

**Frontend:** Rollback button in App.tsx control rack

**Rebuild:** Removed entirely from v1.

---

## F9: Version History + Restore

**Disposition: REMOVE**

**Current behavior:**
- Every significant mutation (split, plan gates, finish, restore) creates a new version snapshot
- `GET /v1/projects/{id}/versions` — returns full version tree (parent-child relationships)
- `GET /v1/projects/{id}/versions/{id}/snapshot` — loads a historical snapshot
- `POST /v1/projects/{id}/versions/{id}/restore` — restores to a previous version
- Preview mode: view a historical snapshot without mutations being blocked
- `VersionNavigator.tsx` — sidebar showing version history tree with preview/restore buttons

**Backend:** `Orchestrator.list_versions()`, `Orchestrator.restore_version()`, `storage.py` versions management

**Frontend:** `VersionNavigator.tsx` (~158 lines), preview mode in `App.tsx`

**Rebuild:** Removed entirely from v1.

---

## F10: Audit Trail (SSE Events)

**Disposition: REMOVE**

**Current behavior:**
- Every mutation appends an event to `audit.ndjson` (26 event types)
- `GET /v1/projects/{id}/events?from_seq={seq}` — SSE stream of audit events from a sequence number
- Frontend SSE manager subscribes on project load, reconnects with backoff
- Events drive snapshot refresh and version list refresh in UI

**Backend:** `storage.py` audit append, `routers/events.py` SSE stream

**Frontend:** `sseManager.ts`, `store.ts` (WsState with lastSeq), `App.tsx` SSE setup

**Rebuild:** Project-wide audit SSE removed. UI refreshes snapshot directly after mutations.

---

## F11: Chat per Node (Breadcrumb Chat)

**Disposition: KEEP / REWRITE**

**Current behavior:**
- Each node has a persistent chat session with the Codex app server
- Chat UI accessible via "Breadcrumb" view — sidebar/overlay showing ancestor path + chat interface
- Session stored per node in `chat_state.json`
- Messages sent to `POST /v1/projects/{id}/nodes/{id}/chat/messages`
- Assistant responses streamed via SSE: `GET /v1/projects/{id}/nodes/{id}/chat/events`
- Session includes: message history, `access_mode`, `cwd`, `writable_roots`, `timeout_sec`
- Chat config editable (access mode, working directory, writable paths)

**Backend:** `chat_service.py`, `codex_app_client.py`, `routers/chat.py`

**Frontend:** `features/breadcrumb/ChatPanel.tsx` (~598 lines), `BreadcrumbView.tsx` (~173 lines)

**Changes in rebuild:**
- Chat session created via Codex app server thread (same subprocess pattern)
- Breadcrumb Workspace becomes **primary execution surface** (not a side panel)
- Chat config editing simplified (remove legacy access_mode complexity)
- Finish Task flow seeds the composer draft from node title + description

---

## F12: Mark Done (Node Completion)

**Disposition: NEW** (replaces legacy `close_node`)

**Current behavior (`close_node`):**
- `POST /v1/projects/{id}/nodes/{id}/close` — marks node `closed`
- No sibling unlock behavior
- Rarely used (most completion via `finish_node`)

**Rebuild:**
- `POST /v1/projects/{id}/nodes/{id}/complete` — marks node `done`
- Triggers sibling unlock: next sibling transitions `locked` → `ready`
- Exposed in UI as "Mark Done" button in Breadcrumb Workspace

---

## F13: Sibling Unlock

**Disposition: NEW** (no equivalent in legacy)

**Current behavior:** No sibling ordering logic. All children created with `draft` status, no ordering enforced.

**Rebuild:**
- When split creates children: first child gets `ready`, rest get `locked`
- When a child is marked `done`: next `locked` sibling transitions to `ready`
- Enforces sequential execution of split children

---

## F14: Theme System

**Disposition: KEEP / SIMPLIFY**

**Current behavior:**
- 5 themes: warm-earth, slate, forest, obsidian, amethyst
- CSS custom properties per theme (colors, borders, shadows, radii)
- Theme stored in `localStorage['planningtree.theme']`
- Implemented via `[data-theme="X"]` attribute selectors on root element
- Theme switcher UI in topbar with color swatches

**Frontend:** `styles.css` lines 1-400 (token definitions per theme), `App.tsx` theme toggle

**Changes in rebuild:**
- Move tokens into `styles/tokens.css` (design tokens only)
- Migrate theme classes to CSS Modules per component
- Keep 5 themes, same palette

---

## F15: Workspace Settings + Bootstrap

**Disposition: NEW / REPLACE**

**Current behavior:** No workspace selection or bootstrap flow. Data root configured entirely via env var. No first-run experience.

**Rebuild:**
- `GET /v1/bootstrap/status` — reports app readiness and whether workspace is configured
- `GET/PATCH /v1/settings/workspace` — read/write base workspace root
- First-run flow in UI: detect unconfigured state, prompt folder selection
- Workspace root stored in `config/app.json`

---

## F16: Metrics + Worker Health

**Disposition: REMOVE**

**Current behavior:**
- `GET /metrics` — operation counters (split, plan, finish, etc.)
- `GET /worker-health` — Codex subprocess status

**Rebuild:** Not part of v1 API surface.

---

## F17: Breadcrumb Navigation

**Disposition: KEEP / REDESIGN**

**Current behavior:**
- `BreadcrumbView.tsx` shows linear ancestor chain from root to selected node
- Each ancestor is a clickable link for navigation
- Currently a secondary view alongside the main graph

**Rebuild:**
- Breadcrumb Workspace becomes the **primary execution surface** (a full page, not a sidebar)
- Contains chat panel, Mark Done button, and ancestor navigation header
- Reached via "Finish Task" action from the graph

---

## F18: Context Lens

**Disposition: REMOVE**

**Current behavior:**
- `ContextLens.tsx` (~67 lines) — metadata dashboard showing snapshot version, audit seq, current gate, unresolved questions, active assumptions, pending reconfirmations, deferred replans, total node count

**Rebuild:** Removed. No replacement in v1.

---

## F19: Reconfirmation Panel

**Disposition: REMOVE**

**Current behavior:**
- `ReconfirmationPanel.tsx` (~67 lines) — shows pending plan reconfirmations (nodes whose gate plan needs replanning due to scope changes)
- Buttons to select impacted nodes and replan

**Rebuild:** Removed (depends on gate system).
