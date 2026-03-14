# Agent Rules — PlanningTree Rebuild

Rules for AI agents (and human developers) working on this codebase.

---

## Before Writing Any Code

1. **Read the feature spec first.** Every feature has a spec in `docs/features/<feature-name>.md`. If the spec doesn't exist, write it before implementing.

2. **Check `docs/audit/REBUILD_CLASSIFICATION.md`** before porting any code from `PlanningTreeCodex`. If a concept is classified REMOVE, do not port it.

3. **Check `docs/audit/DATA_AND_CONTRACTS.md`** for the canonical API surface and storage schema. Do not add endpoints or fields not defined there without documenting the addition.

4. **Check `10_legacy_mapping.md`** if porting any legacy concept to ensure the correct new terminology is used.

---

## Naming Rules

| Legacy Term | Rebuild Term |
|---|---|
| `prompt` (node field) | `description` |
| `short_title` | `title` |
| `finish_node` | `Finish Task` (UI action, not API endpoint) |
| `close_node` | `complete` / `Mark Done` |
| `planned` (status) | `ready` |
| `running` (status) | `in_progress` |
| `closed` (status) | `done` |
| `blocked` (status) | **removed — no equivalent** |
| `gate` / `gate_plan` / `run_gate` | **removed — do not use** |
| `rollback` | **removed — do not use** |
| `version` / `restore` | **removed — do not use** |
| `audit` / `audit event` | **removed — do not use** |

---

## Backend Rules

### Routes
- Routes are **thin**: validate input, call one service method, return the result.
- A route must not query the database/filesystem directly.
- A route must not contain conditional business logic.
- Error handling: catch `AppError`, let it propagate to the global exception handler.

```python
# CORRECT
@router.post("/{project_id}/nodes/{node_id}/split")
async def split_node(project_id: str, node_id: str, body: SplitRequest):
    result = await split_service.split(project_id, node_id, body.mode)
    return result

# WRONG — business logic in route
@router.post("/{project_id}/nodes/{node_id}/split")
async def split_node(project_id: str, node_id: str, body: SplitRequest):
    node = storage.get_node(project_id, node_id)
    if node.status != "ready":
        raise HTTPException(400, "Node is not ready")
    ...
```

### Services
- Services are the **only place** for business rules and domain invariants.
- Services must not call `fetch()`, `requests.get()`, or any HTTP client directly.
- Services must not read/write files directly — call `storage.*` methods.
- Services must not spawn subprocesses — call `ai/codex_client.py` methods.

### Storage
- All JSON reads/writes go through `storage/file_utils.py:atomic_write()`.
- Storage modules must not contain business logic.
- Never write partial state — always write complete JSON objects atomically.

### AI Modules
- `ai/openai_client.py` owns all OpenAI API calls. No other module imports `openai`.
- `ai/codex_client.py` owns all subprocess management. No other module uses `subprocess`.
- Prompt templates live in `ai/split_prompt_builder.py`. No inline prompt strings elsewhere.

---

## Frontend Rules

### Components
- Components must not call `fetch()` — use `api/hooks.ts` or `stores/*`.
- Components must not contain business logic — move to stores.
- Feature components must not import from other feature directories.

```tsx
// CORRECT
const { snapshot } = useProjectStore()

// WRONG
const [snapshot, setSnapshot] = useState(null)
useEffect(() => { fetch('/v1/projects/...').then(...) }, [])
```

### State
- All client state lives in Zustand stores.
- Stores handle API calls and update local state.
- Components are presentational — they read from stores, dispatch store actions.

### Styling
- Component-specific styles: create `ComponentName.module.css` next to the component.
- Design tokens (colors, spacing, radius): `styles/tokens.css` only.
- No inline styles except for truly dynamic values (e.g., computed widths).
- No global class names — use CSS Modules for all component styles.

### Finish Task
- **Finish Task is a client-side navigation action.** It does NOT call any backend endpoint.
- Implementation: save pending node edits → navigate to `/projects/:projectId/nodes/:nodeId/chat` with transient router state → breadcrumb store seeds the local composer.

---

## What to Mark Explicitly

If you are uncertain about any of the following, add a `# TODO(verify):` comment:
- Whether a legacy behavior should be preserved
- Whether a new requirement conflicts with existing behavior
- Whether a dependency has changed semantics between legacy and rebuild

---

## Common Mistakes to Avoid

1. **Copying legacy gate/rollback/version code.** If you are reading `orchestrator.py` for reference, stop when you reach anything involving `gate_plan`, `gate_run`, `current_gate_id`, `rollback`, `version`, or `audit`.

2. **Using the legacy status names.** `planned`, `running`, `blocked`, `closed` are all legacy. Use `ready`, `in_progress`, `done`.

3. **Using `prompt` for the node text field.** Use `description`. The rename is intentional — it reflects that this is a user-visible description, not an AI prompt.

4. **Putting business logic in routes.** If a route method is longer than ~15 lines, you are probably doing something wrong.

5. **Using a global `styles.css`.** Create a `ComponentName.module.css` for each component.

6. **Calling `fetch()` in a component.** Put it in `api/client.ts` and expose it via a hook.

7. **Adding a project-wide SSE audit stream.** There is no project-wide event stream in the rebuild. SSE is for chat only.

---

## Adding a New Feature

1. Write `docs/features/<feature-name>.md` with: current behavior (if porting), desired behavior, domain rules, API changes, acceptance criteria, test plan.
2. Add types/validators to shared types (if backend model changes).
3. Implement service method.
4. Implement storage changes (if needed).
5. Implement route.
6. Implement frontend store action.
7. Implement frontend UI.
8. Write unit tests (backend service + frontend store).
9. Write E2E test (if it's a user-visible flow).
10. Update `docs/features/<feature-name>.md` with actual vs. expected behavior notes.

---

## Reference Files (Read Before Porting)

| Legacy File | What to Port | What to Skip |
|---|---|---|
| `backend/orchestrator.py` | Node CRUD logic, status transition rules | Gate, rollback, version, finish_node |
| `backend/storage.py` | Atomic write pattern, path helpers, project structure | Audit writes, checkpoint writes, version writes |
| `backend/codex_app_client.py` | Subprocess lifecycle, JSON-RPC message format | — |
| `backend/split_planner.py` | Prompt templates, soft caps, phase keys | Gate context, scope fence |
| `backend/context_projection.py` | Ancestor chain construction | Gate context projection |
| `frontend/WorkflowGraph.tsx` | Graph layout, node card structure | Gate action buttons, version preview overlay |
| `frontend/ChatPanel.tsx` | Streaming UI, message display, SSE handling | Chat config editing (access_mode, cwd) |
| `frontend/sseManager.ts` | SSE connection, reconnect with backoff | Audit event tracking (lastSeq) |
