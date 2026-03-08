# Migration Plan — PlanningTree Rebuild

Version: 0.1.0-scaffold
Last updated: 2026-03-07

---

## Strategy

This is a **clean-break rebuild**, not an in-place migration. The legacy codebase at `PlanningTreeCodex` is a read-only reference. No data migration from legacy storage format is planned for v1.

**Migration approach:** One feature group at a time, in dependency order. Each feature is:
1. Specified in `docs/features/<name>.md` before implementation
2. Implemented across all layers (storage → service → route → frontend)
3. Tested before the next feature begins

**Source rules:**
- If a legacy concept exists in `docs/audit/REBUILD_CLASSIFICATION.md` as REMOVE, do not port it
- If a legacy concept maps to a new name in `docs/audit/DATA_AND_CONTRACTS.md`, use the new name
- Port patterns and logic, never paste legacy code directly

---

## Phase Map

| Build Phase | Features |
|---|---|
| Phase 2: Scaffold | Project foundation only (no business logic) |
| Phase 3: Core Graph | Bootstrap, Settings, Projects, Nodes, Status model, Sibling unlock, Mark Done, Graph UI |
| Phase 4: Breadcrumb | Codex client, Chat storage, Chat service, Chat SSE, Finish Task flow, Breadcrumb UI |
| Phase 5: AI Planning | OpenAI client, Context builder, Split prompts, Walking skeleton, Slice, Split UI |
| Phase 6: Polish | Cloud auth, Workspace setup, PyInstaller build, npm packaging |

---

## Feature Migration Queue

Listed in implementation order within each phase. Each item is a unit of work with defined acceptance criteria.

### Phase 3 Queue

#### M01 — Bootstrap + Settings

**Source:** No direct legacy equivalent (new in rebuild)
**Spec:** Create `docs/features/bootstrap-settings.md` before starting

Current behavior: None (no bootstrap or workspace config flow)
Target behavior:
- `GET /v1/bootstrap/status` → `{ ready: bool, workspace_configured: bool }`
- `GET /v1/settings/workspace` → `{ base_workspace_root: string | null }`
- `PATCH /v1/settings/workspace` → sets `base_workspace_root` in `config/app.json`
- Frontend detects unconfigured state on load and shows WorkspaceSetup screen

Dependencies: None
Acceptance: Frontend shows workspace setup on fresh install; shows graph after workspace is set

#### M02 — Project CRUD

**Source:** `orchestrator.py: create_project(), list_projects()`
**Spec:** Create `docs/features/project-crud.md` before starting

Current behavior: Create project with name; list all projects; snapshot has tree with one root node
Target behavior: Same, with simplified storage schema (state.json schema_version: 2)

Dependencies: M01 (workspace must be configured to create projects)
Acceptance: POST /v1/projects creates project with root node; GET /v1/projects lists it; GET /snapshot returns tree

#### M03 — Node CRUD + Status Model

**Source:** `orchestrator.py: create_node(), update_node_prompt()`, `fsm.py`
**Spec:** Create `docs/features/node-crud.md` before starting

Current behavior: Create child nodes; update node `prompt` field; status: locked/draft/planned/running/blocked/closed
Target behavior: Create child nodes; update `title` and `description` fields; status: locked/draft/ready/in_progress/done

Migration notes:
- `prompt` → `description`
- `short_title` → `title`
- `draft` status kept
- `planned` → `ready`
- `running` → `in_progress`
- `closed` → `done`
- `blocked` removed (no gate system to create it)

Dependencies: M02
Acceptance: Create node with title/description; update fields; status field uses new enum

#### M04 — Tree Service + Sibling Unlock

**Source:** No direct equivalent (new behavior in rebuild)
**Spec:** Create `docs/features/sibling-unlock.md` before starting

Current behavior: No sibling ordering. All children created `draft`, no ordering enforced.
Target behavior:
- When split creates children: first child = `ready`, rest = `locked`
- When a node is completed: next `locked` sibling transitions to `ready`
- `tree_service.unlock_next_sibling(project_id, completed_node_id)`

Dependencies: M03
Acceptance: Split creates children with correct status ordering; marking first done makes second ready

#### M05 — Mark Done (Complete Endpoint)

**Source:** `orchestrator.py: close_node()` (partial reference only)
**Spec:** Create `docs/features/mark-done.md` before starting

Current behavior: `close_node()` marks node `closed`; no sibling unlock
Target behavior: `POST /complete` marks node `done`; triggers `tree_service.unlock_next_sibling()`

Dependencies: M04
Acceptance: Leaf node can be completed; next sibling becomes ready; non-leaf completion returns 409

#### M06 — Graph Workspace UI

**Source:** `frontend/features/graph/WorkflowGraph.tsx` (layout patterns only — not gate actions)
**Spec:** Create `docs/features/graph-workspace.md` before starting

Current behavior: ReactFlow graph with 1,554-line monolithic component; includes gate buttons
Target behavior: @xyflow/react graph decomposed into GraphWorkspace + TreeGraph + GraphNode + GraphControls; no gate buttons

Migration notes:
- Use `@xyflow/react` (reactflow successor; same API, better maintained)
- Port graph layout algorithm from legacy WorkflowGraph.tsx
- Port node card structure and status color logic
- Remove: Plan Gates button, Run Gate button, rollback controls, version preview overlay
- Add: Finish Task button (triggers navigation, no API call)
- Split buttons (walking_skeleton, slice) added as stubs pointing to Phase 5

Dependencies: M02, M03, M05
Acceptance: Graph renders project tree; nodes show correct status colors; Finish Task navigates to breadcrumb

---

### Phase 4 Queue

#### M07 — Codex App Server Client

**Source:** `backend/codex_app_client.py` (port + clean up, keep Python)
**Spec:** Create `docs/features/codex-client.md` before starting

Current behavior: Python subprocess management, stdio JSON-RPC, stream reading, thread ID tracking
Target behavior: Same pattern, cleaner implementation in `backend/ai/codex_client.py`

Migration notes:
- Port subprocess lifecycle management
- Clean up stdio buffering (Windows line ending handling)
- Remove gate-specific message types
- Keep: chat session creation, message sending, stream reading, thread resume

Dependencies: None (independent)
Acceptance: Unit tests with mock subprocess; integration test with real Codex binary (if available)

#### M08 — Chat Storage + Service

**Source:** `backend/chat_service.py`, `backend/storage.py (chat sections)`
**Spec:** Create `docs/features/chat-service.md` before starting

Current behavior: Per-node chat sessions stored in chat_state.json; session includes messages + config
Target behavior: Same structure, simplified config (remove access_mode, cwd, writable_roots from public model); add composer_draft field

Dependencies: M07
Acceptance: Create session; send message; session persists across restarts; draft field persisted

#### M09 — Chat SSE + Routes

**Source:** `backend/routers/chat.py`, `backend/streaming/`
**Spec:** Covered in `docs/features/chat-service.md`

Current behavior: SSE stream emits chat events (text deltas, completion, error); ChatEventBroker pub/sub
Target behavior: Same pattern, implemented in `backend/streaming/sse_broker.py`

Dependencies: M08
Acceptance: POST /chat/messages → SSE stream delivers assistant response chunks; reconnect recovers stream

#### M10 — Finish Task Flow (Client-Side)

**Source:** No direct equivalent in legacy (legacy had a backend endpoint)
**Spec:** Create `docs/features/finish-task.md` before starting

Current behavior: POST /finish → marks node closed
Target behavior: Client-side only — save pending edits → navigate to /node/:nodeId/chat → backend seeds composer draft from node title + description

Migration notes:
- Backend: on GET /chat/session when no session exists, create session and seed composer_draft
- Frontend: Finish Task button in graph calls `ui-store.finishTask(nodeId)` which navigates

Dependencies: M06, M09
Acceptance: Click Finish Task → land in Breadcrumb Chat with draft prefilled; no API call on button click itself

#### M11 — Breadcrumb Workspace UI

**Source:** `frontend/features/breadcrumb/BreadcrumbView.tsx`, `ChatPanel.tsx`
**Spec:** Create `docs/features/breadcrumb-workspace.md` before starting

Current behavior: Side panel/overlay with ancestor list + chat; secondary view
Target behavior: Full-page workspace at `/node/:nodeId/chat`; primary execution surface

Migration notes:
- Port ChatPanel streaming UI and SSE integration
- Port BreadcrumbView ancestor chain rendering
- Add Mark Done button (calls M05 complete endpoint)
- Remove: access_mode/cwd/writable_roots config editing
- Remove: chat reset is internal (not exposed as prominent UI action)

Dependencies: M10
Acceptance: Full Finish Task → chat → streaming → Mark Done loop functional end-to-end

---

### Phase 5 Queue

#### M12 — OpenAI Client (Split)

**Source:** No direct equivalent (legacy uses Codex subprocess; rebuild uses OpenAI API directly)
**Spec:** Create `docs/features/openai-split-client.md` before starting

Current behavior: Split called via Codex subprocess JSON-RPC
Target behavior: `backend/ai/openai_client.py` calls OpenAI Responses API with structured output schema

Dependencies: None (independent)
Acceptance: Unit test with mocked openai SDK; returns parsed split result; configurable model

#### M13 — Context Builder

**Source:** `backend/context_projection.py`
**Spec:** Covered in `docs/features/ai-planning.md`

Current behavior: Builds node ancestry chain with gate context, scope fence, layer projections
Target behavior: Simplified — builds ancestry chain (title + description per ancestor node); no gate context

Dependencies: M03
Acceptance: Given a node, returns ordered list of ancestor contexts (id, title, description)

#### M14 — Split Prompt Builder (walking_skeleton)

**Source:** `backend/split_planner.py`
**Spec:** Covered in `docs/features/ai-planning.md`

Current behavior: Builds prompt with phase structure (skeleton → data → logic → polish), gate references, soft caps
Target behavior: Build prompt for walking_skeleton using title/description model; no gate references

Migration notes:
- Remove scope fence / gate context from prompts
- Adapt output format: `{ title: string, description: string }[]` not `{ short_title, prompt }[]`
- Keep soft caps and phase guidance
- Manual review of output quality required before marking done

Dependencies: M13
Acceptance: Prompt generation unit tests; split output contains title + description per child

#### M15 — Split Service + Route (walking_skeleton)

**Source:** `backend/orchestrator.py (split_node)`, `split_graph.py` (simplified)
**Spec:** Covered in `docs/features/ai-planning.md`

Current behavior: LangGraph state graph with drift-retry; up to 3 retries
Target behavior: Direct call to openai_client with simple retry wrapper (max 2 retries on parse failure); no LangGraph

Dependencies: M12, M14, M04
Acceptance: POST /split with mode=walking_skeleton creates children; first=ready, rest=locked

#### M16 — Slice Mode

**Source:** `backend/split_planner.py (slice templates)`
**Spec:** Covered in `docs/features/ai-planning.md`

Current behavior: Separate prompt template focused on vertical slice decomposition
Target behavior: Same, adapted to title/description model

Dependencies: M15
Acceptance: POST /split with mode=slice creates ordered children; output quality comparable to legacy

#### M17 — Split UI in Graph

**Source:** `frontend/features/graph/WorkflowGraph.tsx (split buttons)`
**Spec:** Covered in `docs/features/ai-planning.md`

Current behavior: Walking Skeleton + Slice buttons in node action menu and NodeDetailPanel
Target behavior: Same buttons in GraphControls; loading state during split; graph updates after split

Dependencies: M06, M15, M16
Acceptance: User clicks split button → loading state → children appear in graph with correct status

---

### Phase 6 Queue

#### M18 — Cloud Auth

**Source:** No legacy equivalent
**Spec:** Create `docs/features/auth.md` when auth provider is confirmed

Dependencies: M01
Note: Auth provider not yet chosen. Implement stub in Phase 2-5; integrate in Phase 6.

#### M19 — Workspace Setup UX (Polish)

**Source:** No direct legacy equivalent
**Spec:** Extend `docs/features/bootstrap-settings.md`

Dependencies: M01, M18
Acceptance: New user runs `npx planningtree`, browser opens, workspace prompt appears, user picks folder, lands in graph

#### M20 — PyInstaller Build + npm Distribution

**Source:** No legacy equivalent
**Spec:** Create `docs/features/distribution.md`

Dependencies: All features stable
Acceptance: `npx planningtree` works on Windows, macOS, Linux without Python prerequisite

---

## Risk Register

| Feature | Risk | Mitigation |
|---|---|---|
| M07 (Codex client) | Windows stdio buffering differences | Test on Windows first; handle line endings explicitly |
| M14 (split prompts) | Quality degradation from model change | A/B test against legacy output; manual review |
| M15 (split service) | OpenAI API rate limits or latency | Configurable timeout; clear user feedback during split |
| M20 (PyInstaller) | Binary size + cross-platform CI | GitHub Actions matrix build; target < 30MB per binary |
| M18 (auth) | Provider not yet decided | Stub with always-authenticated until Phase 6 |

---

## Definition of Done (per feature)

A feature migration is complete when:
1. Unit tests pass
2. Integration tests pass
3. E2E test (if applicable) passes
4. Feature spec (`docs/features/<name>.md`) documents any intentional behavior differences from legacy
5. No gate/rollback/version/audit concepts are present in the implementation
6. Code review confirms business logic is in services (not routes or components)
