# Master Plan: CodexMonitor Conversation Into PlanningTree

## Purpose
- Formalize Plan 1 as the authoritative migration baseline.
- Keep PlanningTree's product model intact while migrating CodexMonitor's core conversation UX and semantics.
- Prevent the migration from drifting into shell or panel replacement work.

## Locked Decisions
- Scope is limited to the core conversation/chat experience embedded inside PlanningTree `ask`, `planning`, and `execution` threads.
- PlanningTree breadcrumb, node, task, brief, and spec concepts remain intact.
- Task, brief, and spec are read-only context inputs during this migration.
- Frontend must not talk directly to `codex-app-server`.
- Backend boundary is a thin `ConversationGateway` plus a per-project or per-workspace persistent session manager.
- Rich normalized messages are the durable conversation record.
- Retry, continue, regenerate, cancel, concurrency, reconnect, and replay are first-class requirements.
- Conversation UI migration must not expand into shell migration. Any dependency discovered from CodexMonitor shell or panel structure must be classified explicitly as `adapt_before_migrate`, `stub_temporarily`, or `defer`.

## Authoritative Architecture Direction
### Shared Conversation Embedding
- Build one shared conversation surface under `frontend/src/features/conversation/`.
- Embed that surface inside existing PlanningTree thread hosts:
  - `frontend/src/features/breadcrumb/AskPanel.tsx`
  - `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - `frontend/src/features/breadcrumb/ChatPanel.tsx`
- Preserve mode-specific wrappers:
  - ask packet sidecar remains in ask
  - split controls remain in planning
  - execution framing remains in execution

### Canonical Identity Model
- Canonical fields:
  - `project_id`
  - `node_id`
  - `thread_type`
  - `conversation_id`
  - `app_server_thread_id`
  - `stream_id`
  - `event_seq`
- `thread_type` is the product embedding context and is one of `ask | planning | execution`.
- `conversation_id` is the canonical durable PlanningTree identity.
- `app_server_thread_id` is runtime binding state, never the primary PlanningTree identity.
- `stream_id` owns one active live operation.
- `event_seq` is a reconnect cursor, not the durable replay source of truth.

### Conversation ID Creation Rule
- In this migration phase, `conversation_id` is created lazily when the new conversation subsystem first initializes conversation state for a `(project_id, node_id, thread_type)` tuple.
- Initialization may happen on first thread load, first history read, or first send on the new path.
- If legacy state exists, the first migration read seeds exactly one canonical `conversation_id` for that tuple.

### Phase-1 Durable Scope Rule
- In this migration phase, each `(project_id, node_id, thread_type)` owns exactly one canonical `conversation_id`.
- Branching is represented through message and turn lineage inside that conversation.
- Do not create multiple durable conversations for the same tuple unless a later phase explicitly expands the model.

### Thread Type Vs Runtime Mode
- `thread_type` is the product embedding context.
- `runtime_mode` is a session or turn behavior selector.
- `runtime_mode` controls plan or execute semantics, tool policy, approval behavior, and request context layering without changing `thread_type`.

### Runtime Mode Rules
- `thread_type=ask` uses `runtime_mode=ask`.
- `thread_type=planning` uses `runtime_mode=planning`.
- `thread_type=execution` may use `runtime_mode=plan` or `runtime_mode=execute`.
- Store `thread_type` at the conversation level.
- Store current `runtime_mode` at the conversation level and authoritative historical `runtime_mode` at turn or message lineage level when it changes across turns.

### Thread Mode Behavior Contract
| Thread Type | Runtime Mode | Composer | Tool Policy | Plan Semantics | Artifact Write-Back | Required Wrappers |
|---|---|---|---|---|---|---|
| `ask` | `ask` | Enabled | Ask-safe policy | No execution-plan finalization | None | Ask packet sidecar preserved |
| `planning` | `planning` | Disabled by default for the initial embedding and cutover phase; future enablement is outside this migration baseline | Planning-specific policy | Planning-thread rich rendering with split context only | None | Existing split wrappers preserved |
| `execution` | `plan` or `execute` | Enabled | Execution-capable policy | Supports both plan-mode and execute-mode semantics | None | Existing execution framing preserved |

### Prompt Layering Contract
- Every turn request must layer:
  - base system prompt
  - project metadata
  - node metadata
  - `thread_type`
  - `runtime_mode`
  - task context
  - brief context
  - spec context
  - mode-specific instructions
  - tool policy
  - approval policy

### Durable Truth Model
- Persist normalized rich messages as the durable conversation record.
- Persist conversation metadata, lineage metadata, and reconnect cursor metadata alongside them.
- Do not use raw stream events as the durable replay source of truth.
- Replay after reload must reconstruct from normalized rich messages.
- `event_seq` is used for live stream continuation and reconnect only.

### Ordering And Merge Rules
- Only the active `stream_id` may mutate the active turn for a conversation.
- Events from cancelled, superseded, or replaced streams must be ignored.
- Assistant text deltas append to the active `assistant_text` part for the active assistant message.
- Tool, reasoning, plan, approval, and runtime-input parts update by stable upstream identity when available.
- If no stable upstream key exists, append by deterministic normalized part order.
- Persisted display ordering follows normalized message and part order, not raw arrival order when conflicts occur.

### Persistence Timing Guarantees
- Hot-path stream forwarding must not wait on durable persistence.
- Persistence is forward-first, persist-after.
- Partial assistant deltas may batch before durable write.
- Terminal states must flush promptly on completion, interruption, cancellation, or final error.
- Approval requests, runtime input requests, final usage, final error, lineage transitions, supersede markers, and terminal stream ownership changes must be durably written eagerly.

### Runtime Semantics Contract
| Action | Expected UX | Lineage Effect | Runtime Strategy | Fallback Strategy |
|---|---|---|---|---|
| `cancel` | Stop active response immediately | No new lineage node | Interrupt active `stream_id` and turn | Mark stale if runtime already ended |
| `continue` | Continue conversation from same durable thread | New continuation node on same lineage | New turn on same app-server thread | Fork only if thread is unrecoverable |
| `retry` | Re-run prior user turn | New branch linked to prior user turn | Re-run against same conversation lineage | Fork-based branch if rewind unavailable |
| `regenerate` | Replace or supersede prior assistant answer | New assistant node supersedes old answer | Prefer rollback or rewind if runtime supports it | Fork-based sibling answer with supersede metadata |

### Gateway And Session Direction
- Add a thin backend `ConversationGateway`.
- Add a per-project or per-workspace `SessionManager`.
- Request setup path does context building, session resolution, lineage intent, and stream ownership binding.
- Hot stream path forwards events quickly, stamps ownership metadata, rejects stale streams, and persists normalized updates in parallel.
- Phase 2 remains backend-only and execution-only.
- Phase 2 `P2.1` adds only the project-scoped session manager skeleton.
- Phase 2 `P2.2` adds only the execution-scoped conversation-v2 `get`, `send`, and `events` path in parallel to legacy routes.
- No ask or planning v2 routes ship in Phase 2.
- No UI cutover ships in Phase 2.

### Phase 2 Execution-Only Defaults
- `GET /v2/.../conversations/execution` is durable-store-first and may enrich the snapshot with live ownership metadata if a project session is active.
- `POST /v2/.../conversations/execution/send` is execution-only and must reject non-execution-eligible nodes.
- The assistant placeholder `message_id` is created at send-start and remains the stable assistant target for all delta and final text updates of that turn.
- All ownership reads and writes for `active_streams`, `active_turns`, and `loaded_runtime_threads` must happen under the project session lock.
- Infrastructure-level concurrency remains supported within a project session.
- Execution-specific single-active orchestration is enforced separately at the execution conversation level and does not change the project-scoped session reuse model.

### Rollout And Rollback Strategy
- Introduce a conversation-v2 path in parallel with the current `/chat`, `/ask`, and `/planning` flows.
- Cut over in this order:
  - execution first
  - ask second
  - planning third
- If the new path is unstable, execution may temporarily fall back to the legacy path while preserving the new contracts.
- Legacy removal is forbidden before replay fidelity, concurrency checks, reconnect stability, stale stream rejection, and wrapper regressions are cleared.

## Definition Of Done
- Phase 0 artifacts are complete and internally consistent.
- Phase 1 contracts compile and document the durable truth model.
- Phase 2 proves one execution conversation streams end to end with correct session reuse, isolation, reconnect safety, stale stream rejection, and replayable persistence.
- Phase 3 cuts execution over to the shared surface without breaking existing execution framing.
- Phase 4 embeds ask and planning without breaking packet sidecar or split wrappers.
- Phase 5 reaches CodexMonitor-like semantics for reasoning, tools, plan blocks, approvals, runtime input, diffs, and lineage-aware actions.
- Phase 6 validates performance, concurrency, replay fidelity, and removes compatibility code only after gates pass.
