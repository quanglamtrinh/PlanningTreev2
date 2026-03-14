# Ask Thread & Delta Context Packets

## Goal

Add per-node **ask threads** for scoped user Q&A about a node's plan, and
**delta context packets** that bridge important ask-thread insights back into
the planning thread -- gated by a strict **split guard** that freezes the
planning artifact once children have been created from it.

## Status

| Phase | Status | Notes |
|-------|--------|-------|
| A -- Storage Layer | Implemented | Ask state, snapshot fields, storage methods, and storage tests are in place |
| B -- Ask Service | Implemented | Ask session/message/reset/SSE flow is live |
| C -- Delta Context Packets | Implemented | Packet CRUD, tool-call capture, packet SSE, and split-aware creation rejection are live |
| D -- Merge + Split Guard | Implemented | Packet merge, split preflight enforcement, completion invalidation, and merge-time `503` handling are live |
| E -- Frontend | Implemented | Ask tab, ask store/SSE hook, packet cards, and planning `context_merge` rendering are live |

---

## Design Principles

1. **Planning thread is the source of truth** -- all persistent context that informs splits and gets inherited by children lives in the planning thread.
2. **Ask thread is ephemeral Q&A** -- conversational, scoped to one node, not inherited by children.
3. **Delta context is the bridge** -- the only sanctioned mechanism for ask-thread insights to flow into the planning thread.
4. **Split is an irrevocable commitment** -- once children exist based on a planning state, that state is frozen with respect to ask-thread-derived mutations.
5. **User controls what merges** -- the agent suggests context extraction; the user approves/rejects before it enters the planning thread.
6. **Existing flows untouched** -- planning threads, execution threads, split, and inheritance work exactly as before.

---

## Core Entities

| Entity | Owner | Inherited? | Purpose |
|--------|-------|-----------|---------|
| Planning Thread | Node planning lifecycle | Yes (children fork from parent) | Canonical planning context; informs splits |
| Ask Thread | Single node | No | User Q&A about the node's plan |
| Delta Context Packet | Ask thread that produced it | No (but merged content IS inherited via planning thread) | Distilled insight bridging ask -> planning |
| Execution Thread | Node task lifecycle | No | Task completion chat (unchanged) |

---

## Data Model

### `thread_state.json` -- new `ask` section per node

Each node entry gains a third key alongside `planning` and `execution`:

```python
def _default_ask_state() -> dict[str, Any]:
    return {
        "thread_id": None,                       # Codex thread ID
        "forked_from_planning_thread_id": None,   # Planning thread ID at fork time
        "status": None,                           # None | "idle" | "active"
        "active_turn_id": None,                   # Non-null while agent is responding
        "messages": [],                           # Chat messages (same shape as execution)
        "event_seq": 0,                           # SSE dedup counter
        "delta_context_packets": [],              # List of DeltaContextPacket dicts
        "created_at": None,
    }
```

Ask-thread identity lives primarily in `thread_state.ask.thread_id`. The node
document model also reserves `ask_thread_id` in `state.yaml`, but ask-thread
runtime state does not depend on a duplicated `tree.json` field.

### Public snapshot (via `SnapshotViewService`)

Inject:

```python
"has_ask_thread": bool             # derived from thread_state.ask.thread_id
"ask_thread_status": str | None    # from thread_state.ask.status
```

`ask.event_seq` increments once per persisted ask-visible mutation. Packet
state-machine enforcement belongs to AskService in a later phase, not to
`ThreadStore`.

### Delta Context Packet

```python
{
    "packet_id": str,                  # "dctx_<uuid>"
    "node_id": str,
    "created_at": str,                 # ISO timestamp
    "source_message_ids": [str],       # Which ask messages produced this
    "summary": str,                    # Human-readable one-liner
    "context_text": str,               # Context to inject into planning thread
    "status": str,                     # see state machine below
    "status_reason": str | None,       # Why blocked/rejected
    "merged_at": str | None,           # ISO timestamp when merged
    "merged_planning_turn_id": str | None,
    "suggested_by": str,               # "agent" | "user"
}
```

For agent-suggested packets, `source_message_ids` records the ask exchange that
produced the suggestion in `[user_message_id, assistant_message_id]` order.

**Packet state machine:**

```
                     user approves        system merges
         pending ──────────────────> approved ──────────────> merged (terminal)
           |                            |
           | user rejects               | user rejects before merge
           v                            v
       rejected (terminal)          rejected (terminal)

         pending/approved ─────────────────────────────────> blocked (terminal)
                     node becomes non-mutable (done/superseded)
```

---

## Context Flow & Merge Policy

### When merge is ALLOWED

All conditions must be true:

1. Packet status is `approved`
2. Node has **no active children** (`tree_service.active_child_ids()` returns `[]`)
3. Node is not `done` or `is_superseded`
4. Planning thread is `idle` (no active split turn)
5. Ask thread is `idle` (no active ask turn)

### How merge works

1. **Lazy ensure when needed**: if the node has no local `planning_thread_id`, ask the existing thread lifecycle to create one before merge continues.
2. **Pre-check + reservation under lock**: verify all 5 conditions and reserve planning `status="active"` with a merge turn id before leaving the lock.
3. **Codex turn outside the lock**: run a hidden planning-thread turn injecting `packet.context_text`.
4. **Post-check + atomic commit under lock**: re-verify the reservation and node state, then atomically append a `context_merge` planning turn and update the packet to `merged`.

If an existing planning thread id points to a backend thread that no longer
exists, merge returns a retryable `503 merge_planning_thread_unavailable` and
the packet remains `approved`.

The planning turn created by merge:

```python
{
    "turn_id": "<merge_turn_id>",
    "role": "context_merge",
    "content": packet["context_text"],
    "summary": packet["summary"],
    "packet_id": packet["packet_id"],
    "timestamp": iso_now(),
    "is_inherited": False,
    "origin_node_id": node_id,
}
```

This turn is visible in planning history and gets inherited by children.

### Why the split guard exists

Children are created from the planning state at split time. Post-split mutations would:

- Silently diverge the parent's context from what children were built on
- No automatic propagation mechanism exists to update children
- Plan quality degrades without anyone noticing

If the user learns something important after split, they should address it at the child level or re-split the parent (which creates fresh children from current context).

---

## Split-Aware Lifecycle

### Before split (full capabilities)

User asks question -> agent answers -> agent may suggest delta_context_packet via
tool call -> user approves or rejects -> approved packets block split until they
are merged or rejected -> next split only proceeds once no `pending` or
`approved` packets remain.

### After split (Q&A-only mode)

User asks question -> agent answers -> ask conversation continues for reference,
but no new parent-level packets are materialized:

- manual packet creation returns `409`
- agent `emit_render_data` suggestions are ignored and logged
- no packet is appended and no packet SSE event is published

### At split time (preflight gate, implemented in Phase D)

Split is rejected while the node still has any unresolved parent-level packets:

```python
if any(packet["status"] in {"pending", "approved"} for packet in node_packets):
    raise SplitNotAllowed("Resolve ask-thread delta context packets before splitting this node.")
```

This guard runs before child creation. Split does not auto-block or rewrite
packets as a side effect.

This rule is now enforced by `SplitService` in the same critical section that
reserves planning `active` for the split turn, so unresolved packet checks and
split start are atomic.

### After node completion (implemented in Phase D)

- ask mutations are read-only when the node is `done` or `is_superseded`
- all `pending` and `approved` packets transition to `blocked`
- the same invalidation applies to parents that become `done` through cascade

---

## Ask Thread Agent Behavior

### Current implementation (Phase C)

```python
def build_ask_base_instructions() -> str:
    return (
        "You are the PlanningTree Ask assistant for a specific planning node.\n\n"
        "Your role is to answer questions about this node's plan, clarify scope, "
        "identify risks, surface dependencies, and help the user explore alternatives.\n\n"
        "You are operating inside a per-node ask thread that inherits planning context "
        "from the node's planning thread.\n\n"
        "Focus on explanation and analysis. Do not claim to have changed the plan or "
        "the workspace unless the user explicitly asks for execution in a different flow.\n\n"
        "When the conversation surfaces a materially new insight, risk, dependency, scope "
        "clarification, or decision that should be preserved in planning context, call "
        "emit_render_data with kind='delta_context_suggestion'. Include a short summary "
        "and the full context text to preserve. Do not emit this tool call for every answer."
    )
```

Phase B shipped the ask-service flow without dynamic tools. Phase C extends the
same ask-thread prompt contract with packet suggestion and interception.

### Phase C extension: tool definition

Phase C reuses the existing `emit_render_data` pattern:

```python
def ask_thread_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_render_data",
        "description": "Suggest capturing a new planning insight from this conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["delta_context_suggestion"]},
                "payload": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "context_text": {"type": "string"},
                    },
                    "required": ["summary", "context_text"],
                },
            },
            "required": ["kind", "payload"],
        },
    }
```

### Access mode

Read-only (`access_mode: "read_only"`). The ask thread can read files for
context but cannot modify them.

---

## API Routes

### Phase B routes

```
# Session management
GET  /v1/projects/{pid}/nodes/{nid}/ask/session
POST /v1/projects/{pid}/nodes/{nid}/ask/messages      { content: str }
POST /v1/projects/{pid}/nodes/{nid}/ask/reset

# SSE stream
GET  /v1/projects/{pid}/nodes/{nid}/ask/events
```

Phase B public `AskSession` payload:

```python
{
    "project_id": str,
    "node_id": str,
    "active_turn_id": str | None,
    "event_seq": int,
    "status": str | None,
    "messages": list[dict[str, Any]],
    "delta_context_packets": list[dict[str, Any]],
}
```

The public session does not expose `thread_id`,
`forked_from_planning_thread_id`, `created_at`, or runtime config.

### Phase C routes

```
# Delta context packets
GET  /v1/projects/{pid}/nodes/{nid}/ask/packets
POST /v1/projects/{pid}/nodes/{nid}/ask/packets        { summary, context_text, source_message_ids? }
POST /v1/projects/{pid}/nodes/{nid}/ask/packets/{id}/approve
POST /v1/projects/{pid}/nodes/{nid}/ask/packets/{id}/reject
```

Phase D route:

```
POST /v1/projects/{pid}/nodes/{nid}/ask/packets/{id}/merge
```

### SSE events by phase

Phase B:

```
ask_message_created      { active_turn_id, user_message, assistant_message }
ask_assistant_delta      { message_id, delta, content, updated_at }
ask_assistant_completed  { message_id, content, updated_at }
ask_assistant_error      { message_id, content, updated_at, error }
ask_session_reset        { session }
```

Phase C:

```
ask_delta_context_suggested  { packet }
ask_packet_status_changed    { packet }
```

---

## Frontend Integration

### BreadcrumbWorkspace tab

Frontend Phase E adds `'ask'` to the `TabId` union between `'planning'` and
`'execution'`:

```typescript
type TabId = 'planning' | 'ask' | 'execution' | 'info' | 'spec'
```

### New components

| Component | Purpose |
|-----------|---------|
| `AskPanel.tsx` | Chat UI for ask thread (mirrors `ChatPanel`) |
| `DeltaContextCard.tsx` | Packet card with Approve/Reject/Merge actions |

### New store: `ask-store.ts`

Implemented in Phase E. Mirrors `chat-store.ts` for:

- ask session state
- composer draft
- connection status
- packet approve/reject/merge actions
- ask-prefixed SSE event application

### New types in `api/types.ts`

```typescript
interface AskSession {
  project_id: string
  node_id: string
  active_turn_id: string | null
  event_seq: number
  status: 'idle' | 'active' | null
  messages: ChatMessage[]
  delta_context_packets: DeltaContextPacket[]
}

interface DeltaContextPacket {
  packet_id: string
  node_id: string
  source_message_ids: string[]
  summary: string
  context_text: string
  status: 'pending' | 'approved' | 'merged' | 'rejected' | 'blocked'
  status_reason: string | null
  suggested_by: 'agent' | 'user'
  created_at: string
  merged_at: string | null
}
```

### New SSE hook: `useAskSessionStream`

Implemented in Phase E. Uses the same buffering/resync pattern as
`useChatSessionStream`, but connects to ask routes and applies `AskEvent`
payloads through `ask-store`.

---

## Edge Cases & Safeguards

### Split preflight guard

1. Split fast-fails while any packet is `pending` or `approved`.
2. `approved` continues to block split until the packet is either merged or rejected.
3. Split does not mutate packet state; it only refuses to proceed until the packet set is resolved.
4. After split exists, parent ask stays available for Q&A but packet creation is disabled on that node.

### Re-split

Node still has active children (new ones) after re-split. Parent ask remains
Q&A-only and no new parent-level packets are created.

### Ask thread before planning thread exists

`ensure_ask_thread()` calls `thread_service.ensure_planning_thread()` first.

### Planning thread becomes unavailable

During merge: fail with retryable error, packet stays `approved`. During ask conversation: recreate ask thread.

### Multiple pending packets

Independent lifecycles. Split remains blocked until all `pending` and
`approved` packets have been resolved.

### Stale ask turns on server restart

`reconcile_interrupted_ask_turns()`: clear `active_turn_id`, mark pending assistant messages as error.

---

## Implementation Phases

| Phase | Status | Scope | Dependencies |
|-------|--------|-------|-------------|
| **A -- Storage Layer** | Implemented | Data model, ThreadStore methods, error classes, SnapshotViewService, frontend types | None |
| **B -- Ask Service** | Implemented | AskService (session + messages), ask_prompt_builder, AskEventBroker, routes, main.py wiring | Phase A |
| **C -- Delta Context Packets** | Implemented | Packet CRUD, `pending -> approved`, `pending -> rejected`, `approved -> rejected`, agent tool call interception, split-aware packet creation rejection, packet routes | Phase B |
| **D -- Merge + Split Guard** | Implemented | `merge_packet`, merge route, planning-active reservation, split preflight guard for unresolved packets, completion invalidation, retryable `503` on unavailable planning thread | Phase C |
| **E -- Frontend** | Implemented | `ask-store`, `useAskSessionStream`, `AskPanel`, `DeltaContextCard`, `BreadcrumbWorkspace` Ask tab, and `context_merge` planning rendering | Phase D |

### Locked decisions for implemented Phase C, Phase D, and Phase E

- After split, manual packet creation returns `409`; agent packet suggestions are ignored and logged.
- Split is blocked while any packet is `pending` or `approved`.
- `approved -> rejected` is allowed so the user can reopen split before merge exists.
- Packet mutations stay on the AskService full-session write path; `ThreadStore` packet helpers remain primitives, not the hot path.
- Merge reserves planning `status="active"` before the hidden Codex turn so split and completion cannot race it.
- Merge returns `503 merge_planning_thread_unavailable` when a previously known planning thread is missing on the backend; the packet stays `approved`.
- Frontend Phase E does not expose manual packet creation UI.
- Packet cards are shown in a separate AskPanel section below messages and above the composer.
- `useAskSessionStream()` connects when the Ask tab is active even if no ask thread exists yet, so ask-thread creation stays lazy.

---

## Phase A -- Storage Layer (Detailed)

This phase is implemented. The checklist below tracks the storage milestone that
was shipped; some files were later extended by subsequent phases.

### Critical files

| File | Changes |
|------|---------|
| `backend/storage/thread_store.py` | Add `_default_ask_state`, update `_ensure_node_state_unlocked`/`_default_node_state`/`peek_node_state`, add 5 new methods |
| `backend/services/snapshot_view_service.py` | Derive `has_ask_thread`, `ask_thread_status` |
| `backend/errors/app_errors.py` | Add 5 error classes |
| `frontend/src/api/types.ts` | Add `has_ask_thread`, `ask_thread_status` to `NodeRecord` |

### Checklist

- [x] **A.1** Add `_default_ask_state()` to `backend/storage/thread_store.py`
  ```python
  def _default_ask_state() -> dict[str, Any]:
      return {
          "thread_id": None,
          "forked_from_planning_thread_id": None,
          "status": None,
          "active_turn_id": None,
          "messages": [],
          "event_seq": 0,
          "delta_context_packets": [],
          "created_at": None,
      }
  ```

- [x] **A.2** Update `_ensure_node_state_unlocked()` (line 178)
  - Add: `node_state.setdefault("ask", _default_ask_state())`

- [x] **A.3** Update `_default_node_state()` (line 184)
  - Add `"ask": _default_ask_state()` to the return dict

- [x] **A.4** Update `peek_node_state()` (line 63)
  - Add: `node_state.setdefault("ask", _default_ask_state())` alongside the existing planning/execution setdefaults

- [x] **A.5** Add `get_ask_state(project_id, node_id) -> dict`
  - Lock-guarded read of `state[node_id]["ask"]`
  - Returns deep copy; ensures default if absent

- [x] **A.6** Add `set_ask_status(project_id, node_id, *, thread_id, forked_from_planning_thread_id, status, active_turn_id) -> dict`
  - Uses a sentinel-based update contract so explicit `None` can clear fields
  - Updates `ask.thread_id`, `ask.forked_from_planning_thread_id`, `ask.status`, `ask.active_turn_id`
  - Bumps `ask.event_seq` once when a visible field changes
  - No-op when incoming values are identical

- [x] **A.7** Add `append_ask_message(project_id, node_id, message) -> dict`
  - Appends to `ask.messages`, increments `ask.event_seq`
  - Returns deep copy of ask state

- [x] **A.8** Add `upsert_delta_context_packet(project_id, node_id, packet) -> dict`
  - If packet with matching `packet_id` exists: replace it
  - Otherwise: append to `ask.delta_context_packets`
  - Storage does not enforce packet state transitions
  - Returns deep copy of the packet

- [x] **A.9** Add `block_mergeable_ask_packets(project_id, node_id, *, reason) -> int`
  - Transitions all `pending`/`approved` packets to `blocked` with given reason
  - Returns count of packets blocked
  - Used by invalidation flows when a node becomes non-mutable (for example completion/supersede)

- [x] **A.10** Update `SnapshotViewService.to_public_snapshot()` (line 10 in `snapshot_view_service.py`)
  - Read `ask_state` from `node_thread_state.get("ask", {})`
  - Resolve ask-thread presence from `ask_state.get("thread_id")`
  - Set `raw_node["has_ask_thread"]` = bool check on resolved thread id
  - Set `raw_node["ask_thread_status"]` = `ask_state.get("status")`

- [x] **A.11** Add 5 error classes to `backend/errors/app_errors.py`
  ```python
  class AskTurnAlreadyActive(AppError):
      def __init__(self) -> None:
          super().__init__("ask_turn_already_active",
              "An ask turn is already in progress for this node.", 409)

  class MergeBlockedBySplit(AppError):
      def __init__(self, node_id: str) -> None:
          super().__init__("merge_blocked_by_split",
              f"Cannot merge delta context: node {node_id!r} has been split.", 409)

  class PacketNotFound(AppError):
      def __init__(self, packet_id: str) -> None:
          super().__init__("packet_not_found",
              f"Delta context packet {packet_id!r} not found.", 404)

  class InvalidPacketTransition(AppError):
      def __init__(self, from_status: str, to_status: str) -> None:
          super().__init__("invalid_packet_transition",
              f"Cannot transition packet from '{from_status}' to '{to_status}'.", 409)

  class AskThreadReadOnly(AppError):
      def __init__(self) -> None:
          super().__init__("ask_thread_read_only",
              "Ask thread is read-only because this node is no longer mutable.", 409)
  ```

- [x] **A.12** Add to `NodeRecord` in `frontend/src/api/types.ts` (after line 39)
  ```typescript
  has_ask_thread: boolean
  ask_thread_status: 'idle' | 'active' | null
  ```

- [x] **A.13** Unit tests: `backend/tests/unit/test_thread_store_ask.py`
  - `test_default_ask_state_included_on_ensure` -- verify `_ensure_node_state_unlocked` includes `ask`
  - `test_peek_node_state_includes_ask` -- verify `peek_node_state` returns ask section
  - `test_get_ask_state_returns_default` -- new node returns empty default
  - `test_set_ask_status_updates_fields` -- thread_id, forked_from_planning_thread_id, status, active_turn_id
  - `test_append_ask_message_increments_event_seq`
  - `test_upsert_delta_context_packet_insert` -- new packet appended
  - `test_upsert_delta_context_packet_update` -- existing packet replaced by packet_id
  - `test_block_mergeable_ask_packets_blocks_pending_and_approved`
  - `test_block_mergeable_ask_packets_skips_terminal_statuses`
  - `test_block_mergeable_ask_packets_returns_count`

- [x] **A.14** Unit tests: `backend/tests/unit/test_delta_context_packet.py`
  - `test_packet_insert_preserves_all_fields`
  - `test_packet_upsert_replaces_by_packet_id`
  - `test_packet_upsert_appends_for_distinct_packet_ids`
  - `test_block_only_affects_pending_and_approved_packets`
  - `test_storage_layer_does_not_enforce_packet_transition_policy`

---

## Phase B -- Ask Service (Detailed)

This phase is implemented. The checklist below tracks the ask-service milestone
that was shipped; several files were later extended in Phase C, so these items
describe the Phase B baseline rather than the final file contents.

### Critical files

| File | Changes |
|------|---------|
| `backend/ai/ask_prompt_builder.py` | Add ask base instructions only; no render tool yet |
| `backend/errors/app_errors.py` | Add `AskBlockedByPlanningActive`; neutralize `AskThreadReadOnly` wording |
| `backend/storage/thread_store.py` | Add `write_ask_session()` for raw full-session persistence |
| `backend/services/ask_service.py` | Add ask session lifecycle, ask messaging, streaming, stale-turn recovery |
| `backend/streaming/sse_broker.py` | Add `AskEventBroker` |
| `backend/routes/ask.py` | Add ask session, message, reset, and SSE routes |
| `backend/main.py` | Wire ask broker, ask service, ask routes, and startup reconciliation |

### Checklist

- [x] **B.1** Create `backend/ai/ask_prompt_builder.py`
  - Add `build_ask_base_instructions()`
  - Describe ask threads as scoped Q&A for one planning node
  - Do not mention `emit_render_data` in Phase B
  - Do not add `ask_thread_render_tool()` in Phase B

- [x] **B.2** Extend ask-specific errors in `backend/errors/app_errors.py`
  - Add `AskBlockedByPlanningActive` (`409`)
  - Update `AskThreadReadOnly` wording to cover both `done` and `is_superseded`

- [x] **B.3** Add `write_ask_session(project_id, node_id, session) -> dict` to `backend/storage/thread_store.py`
  - Raw full-session replace for `node_state["ask"]`
  - Does not normalize
  - Does not auto-increment `event_seq`
  - Used by `AskService` for streaming updates and stale-turn recovery

- [x] **B.4** Add `AskEventBroker` to `backend/streaming/sse_broker.py`
  - Same pattern as `ChatEventBroker` and `PlanningEventBroker`

- [x] **B.5** Create `backend/services/ask_service.py`
  - Add ask session normalization and public-session filtering
  - Keep ask-thread identity in `thread_state.ask.thread_id` only
  - AskService owns ask-thread lifecycle; do not add `ThreadService.create_ask_thread()`
  - `_ensure_ask_thread()`:
    - reuse existing ask thread when `resume_thread()` succeeds
    - otherwise ensure planning thread, fork from it with `build_ask_base_instructions()`
    - no dynamic tools in Phase B
  - `get_session()`:
    - returns public session without internal thread fields or runtime config
    - performs stale-turn recovery without bumping `event_seq`
  - `create_message()`:
    - rejects empty content
    - rejects `done`/`is_superseded` with `AskThreadReadOnly`
    - rejects planning-active with `AskBlockedByPlanningActive`
    - rejects concurrent ask turns with `AskTurnAlreadyActive`
    - appends user + assistant messages, sets ask status active, and publishes `ask_message_created`
  - Background turn:
    - uses `run_turn_streaming(..., writable_roots=[])`
    - publishes `ask_assistant_delta`, `ask_assistant_completed`, `ask_assistant_error`
    - no packet interception in Phase B
  - `reset_session()`:
    - clears ask thread identity and message history
    - preserves `delta_context_packets`
    - bumps `event_seq` once and publishes `ask_session_reset`
  - `reconcile_interrupted_ask_turns()`:
    - scans `thread_state` only
    - clears stale `active_turn_id`
    - marks latest pending/streaming assistant message as error
    - does not publish SSE events

- [x] **B.6** Create `backend/routes/ask.py`
  - `GET /projects/{project_id}/nodes/{node_id}/ask/session`
  - `POST /projects/{project_id}/nodes/{node_id}/ask/messages`
  - `POST /projects/{project_id}/nodes/{node_id}/ask/reset`
  - `GET /projects/{project_id}/nodes/{node_id}/ask/events`
  - Mirror `chat.py` structure and heartbeat behavior

- [x] **B.7** Update `backend/main.py`
  - Wire `AskEventBroker`
  - Wire `AskService`
  - Call `ask_service.reconcile_interrupted_ask_turns()` in lifespan
  - Include ask router

- [x] **B.8** Extend `backend/tests/unit/test_thread_store_ask.py`
  - `test_write_ask_session_replaces_full_ask_payload`
  - `test_write_ask_session_does_not_auto_increment_event_seq`

- [x] **B.9** Create `backend/tests/unit/test_ask_service.py`
  - empty/default session
  - stale-turn recovery
  - ask message creation
  - ask turn concurrency
  - read-only for `done` and `is_superseded`
  - planning-active rejection
  - ask-thread reuse and recreation
  - reset preserves packets
  - read-only runtime config for Codex calls

- [x] **B.10** Create `backend/tests/integration/test_ask_api.py`
  - default ask session
  - send ask message and complete turn
  - keep live turn active in session reads
  - SSE event streaming
  - missing-node `404`
  - concurrent-turn `409`
  - planning-active `409`
  - done-node `409`
  - superseded-node `409`
  - reset clears messages and hides internal thread identity

---

## Phase C -- Delta Context Packets (Detailed)

This phase is implemented. Packet creation and mutation now flow through
`AskService` full-session writes, and ask turns can emit packet suggestions via
`emit_render_data`.

### Critical files

| File | Changes |
|------|---------|
| `backend/errors/app_errors.py` | Add split-blocked packet mutation error |
| `backend/ai/ask_prompt_builder.py` | Add `ask_thread_render_tool()` and extend ask instructions for packet suggestion |
| `backend/services/ask_service.py` | Add tool-call interception, packet helpers, packet CRUD, split-aware packet rejection |
| `backend/routes/ask.py` | Add packet list/create/approve/reject routes |
| `backend/tests/unit/test_ask_service.py` | Add packet unit coverage |
| `backend/tests/integration/test_ask_api.py` | Add packet route and packet SSE integration coverage |

### Checklist

- [x] **C.1** Extend `backend/errors/app_errors.py`
  - Add `PacketMutationBlockedBySplit`
  - Keep `PacketNotFound` and `InvalidPacketTransition` as packet lifecycle errors

- [x] **C.2** Extend `backend/ai/ask_prompt_builder.py`
  - Add `ask_thread_render_tool()`
  - Update `build_ask_base_instructions()` so ask threads can suggest materially new planning insights

- [x] **C.3** Update ask-thread forking in `backend/services/ask_service.py`
  - Fork ask threads with `dynamic_tools=[ask_thread_render_tool()]`
  - Keep ask-thread identity in `thread_state.ask.thread_id`

- [x] **C.4** Wire tool-call interception in `backend/services/ask_service.py`
  - Attach `on_tool_call` in ask background turns
  - Ignore unknown tools and malformed payloads
  - Build agent packets with `source_message_ids=[user_message_id, assistant_message_id]`
  - Ignore tool-created packets after split, on stale callbacks, and on non-mutable nodes

- [x] **C.5** Add packet helpers in `backend/services/ask_service.py`
  - `_node_has_active_children(...)`
  - `_build_packet(...)`
  - `_reject_packet_creation_after_split(...)`
  - `_find_packet(...)`

- [x] **C.6** Add packet CRUD to `backend/services/ask_service.py`
  - `list_packets(...)`
  - `create_packet(...)`
  - `approve_packet(...)`
  - `reject_packet(...)`
  - Support `pending -> approved`, `pending -> rejected`, and `approved -> rejected`
  - Use `ask_delta_context_suggested` and `ask_packet_status_changed` SSE events

- [x] **C.7** Add packet routes to `backend/routes/ask.py`
  - `GET /projects/{project_id}/nodes/{node_id}/ask/packets`
  - `POST /projects/{project_id}/nodes/{node_id}/ask/packets`
  - `POST /projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/approve`
  - `POST /projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/reject`

- [x] **C.8** Enforce split-aware packet creation behavior
  - Manual create after split returns `409 packet_mutation_blocked_by_split`
  - Agent suggestions after split are ignored and logged
  - No `blocked` packet is materialized as a substitute for a rejected create

- [x] **C.9** Add unit coverage in `backend/tests/unit/test_ask_service.py`
  - agent tool suggestions create packets
  - source message ordering is preserved
  - split-aware rejection/ignore behavior is covered
  - approve/reject transitions and error cases are covered

- [x] **C.10** Add integration coverage in `backend/tests/integration/test_ask_api.py`
  - packet list/create/approve/reject routes
  - agent tool suggestion during ask turn
  - packet SSE events for manual and agent-created packets
  - split-aware `409` behavior for manual create

### Verification snapshot

- `backend/tests/unit/test_ask_service.py`
- `backend/tests/integration/test_ask_api.py`
- `backend/tests/unit/test_delta_context_packet.py`
- `backend/tests/unit/test_thread_store_ask.py`
- full backend suite passed after Phase C implementation

---

## Phase D -- Merge + Split Guard (Detailed)

This phase is implemented. Merge now flows from approved packet state into
persistent planning context, split rejects unresolved packets, and completion
invalidates any remaining mergeable packets.

### Critical files

| File | Changes |
|------|---------|
| `backend/errors/app_errors.py` | Add retryable merge planning-thread error; neutralize planning-active wording |
| `backend/storage/thread_store.py` | Add atomic helper to write ask session and append planning turn in one commit |
| `backend/services/ask_service.py` | Add `merge_packet()`, merge reservation/release helpers, merge preconditions, and `503` translation |
| `backend/routes/ask.py` | Add packet merge route |
| `backend/services/split_service.py` | Add unresolved-packet preflight guard inside the split reservation critical section |
| `backend/services/node_service.py` | Block completion while planning is active; invalidate pending/approved packets for directly completed and cascaded-done nodes |
| `backend/tests/unit/test_ask_service.py` | Add merge unit coverage |
| `backend/tests/integration/test_ask_api.py` | Add merge API coverage |
| `backend/tests/unit/test_split_service.py` | Add unresolved-packet split-guard tests |
| `backend/tests/unit/test_node_service.py` | Add completion invalidation tests |

### Checklist

- [x] **D.1** Extend error and storage contracts
  - Add `MergePlanningThreadUnavailable` (`503`)
  - Update `AskBlockedByPlanningActive` wording to cover all ask-state mutation, not just ask turns
  - Add `write_ask_session_and_append_planning_turn(...)` for atomic ask + planning merge commits

- [x] **D.2** Add merge support to `backend/services/ask_service.py`
  - Add `_assert_merge_preconditions(...)`
  - Add `_release_reserved_merge_turn(...)`
  - Add `merge_packet(...)`
  - Lazily ensure a planning thread only when the node has no local `planning_thread_id`
  - Reserve planning `status="active"` before the hidden merge turn
  - Translate missing backend planning thread errors to `503`
  - Commit merged packet state and `context_merge` planning turn atomically

- [x] **D.3** Add `POST /projects/{project_id}/nodes/{node_id}/ask/packets/{packet_id}/merge`
  - Route is wired in `backend/routes/ask.py`
  - Returns `200` on success, `409` for invalid merge/split/read-only conflicts, `404` for missing packet, and `503` for unavailable planning thread

- [x] **D.4** Enforce split preflight guard in `backend/services/split_service.py`
  - Add `_assert_no_unresolved_ask_packets(...)`
  - Reject split while any packet is `pending` or `approved`
  - Re-run the guard inside the same critical section that reserves planning active for the split turn
  - Split does not auto-block or rewrite packet state

- [x] **D.5** Enforce completion invalidation in `backend/services/node_service.py`
  - Reject `complete_node()` while planning is active
  - Block `pending` and `approved` packets when a node becomes `done`
  - Cascade the same invalidation to parents that become `done` through child completion

- [x] **D.6** Add merge unit coverage
  - `approved -> merged`
  - merge appends `context_merge` planning turn
  - merge prompt includes packet summary and context text
  - merge rejects pending/rejected/already-merged packets
  - merge rejects split/done/planning-active/ask-active states
  - merge returns `503` when planning thread is unavailable

- [x] **D.7** Add merge integration coverage
  - merge route succeeds for approved packets
  - merge route writes `context_merge` planning history
  - merge route rejects unresolved or missing packets appropriately
  - merge route returns retryable `503` when planning thread is unavailable

- [x] **D.8** Add split-guard and completion-invalidation unit coverage
  - split rejects `pending` and `approved` packets
  - split allows `rejected`, `merged`, `blocked`, or no packets
  - completion blocks `pending` and `approved` packets
  - completion leaves terminal packet states unchanged
  - cascaded done status blocks parent packets

### Verification snapshot

- `python -m pytest backend/tests/unit/test_thread_store_ask.py -q`
- `python -m pytest backend/tests/unit/test_ask_service.py -q`
- `python -m pytest backend/tests/integration/test_ask_api.py -q`
- `python -m pytest backend/tests/unit/test_split_service.py -q`
- `python -m pytest backend/tests/unit/test_node_service.py -q`
- `python -m pytest backend/tests/ -q`

---

## Phase E -- Frontend (Detailed)

This phase is implemented. The Ask backend is now surfaced in the breadcrumb
workspace and packet merges are visible in planning history.

### Critical files

| File | Changes |
|------|---------|
| `frontend/src/api/types.ts` | Add `DeltaContextPacket`, `AskSession`, `AskEvent`; extend `PlanningTurn` with `context_merge` |
| `frontend/src/api/client.ts` | Add ask session/message/reset/events and packet approve/reject/merge methods |
| `frontend/src/api/hooks.ts` | Add `useAskSessionStream()` |
| `frontend/src/stores/ask-store.ts` | Add ask Zustand store with ask SSE event application and packet actions |
| `frontend/src/features/breadcrumb/AskPanel.tsx` | Add ask-thread chat panel |
| `frontend/src/features/breadcrumb/DeltaContextCard.tsx` | Add packet card UI with Approve/Reject/Merge actions |
| `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx` | Add `Ask` tab and ask stream wiring |
| `frontend/src/features/breadcrumb/PlanningPanel.tsx` | Render `context_merge` planning turns explicitly |
| `frontend/tests/unit/ask-store.test.ts` | Add ask-store event and packet action coverage |
| `frontend/tests/unit/ask-session-stream.test.tsx` | Add ask SSE hook coverage |
| `frontend/tests/unit/BreadcrumbWorkspace.test.tsx` | Cover Ask tab wiring and route-state activation |
| `frontend/tests/unit/PlanningPanel.test.tsx` | Cover `context_merge` rendering |

### Checklist

- [x] **E.1** Extend `frontend/src/api/types.ts`
  - Add `PacketStatus`, `DeltaContextPacket`, `AskSession`, and `AskEvent`
  - Extend `PlanningTurn.role` with `context_merge`
  - Add optional `summary` and `packet_id` to planning turns

- [x] **E.2** Extend `frontend/src/api/client.ts`
  - Add ask session/message/reset/events methods
  - Add packet approve/reject/merge client methods
  - Manual packet creation UI remains deferred even though the backend route exists

- [x] **E.3** Add `frontend/src/stores/ask-store.ts`
  - Mirror `chat-store.ts` for ask-session state
  - Apply ask-prefixed SSE events with `event_seq` deduplication
  - Upsert packets by `packet_id`
  - Locally upsert approve/reject/merge responses without synthesizing `event_seq`

- [x] **E.4** Add `useAskSessionStream()` in `frontend/src/api/hooks.ts`
  - Mirror the chat SSE buffering/resync flow
  - Connect on the Ask tab even when `node.has_ask_thread === false`
  - Clear ask-session state when project or node becomes null

- [x] **E.5** Add `Ask` tab to `frontend/src/features/breadcrumb/BreadcrumbWorkspace.tsx`
  - Insert Ask between Planning and Execution
  - Honor route state with `activeTab: 'ask'`
  - Render `AskPanel`
  - Start ask SSE streaming only while the Ask tab is active

- [x] **E.6** Add `frontend/src/features/breadcrumb/AskPanel.tsx`
  - Mirror chat UI structure for ask messages
  - Show ask-specific empty state text
  - Show read-only banner for `done` / `is_superseded`
  - Show split banner when the node has active children
  - Keep ask packet cards in a separate section below messages and above the composer
  - Reset clears ask messages but preserves packets

- [x] **E.7** Add `frontend/src/features/breadcrumb/DeltaContextCard.tsx`
  - Render summary, context preview, status badge, and source indicator
  - Show `Approve` / `Reject` for `pending`
  - Show `Merge` / `Reject` for `approved`
  - Use local pending state for per-card button disabling

- [x] **E.8** Add CSS modules for AskPanel and packet cards
  - Preserve the existing breadcrumb/chat visual language
  - Add ask-specific banners and packet card styles

- [x] **E.9** Update `frontend/src/features/breadcrumb/PlanningPanel.tsx`
  - Render `context_merge` turns as first-class planning entries
  - Show `Context Merge` label plus summary/content
  - Preserve existing split payload rendering for `tool_call`

- [x] **E.10** Add/update frontend unit tests
  - `ask-store.test.ts`
  - `ask-session-stream.test.tsx`
  - `BreadcrumbWorkspace.test.tsx`
  - `PlanningPanel.test.tsx`

### Verification snapshot

- `npx tsc -p tsconfig.app.json --noEmit` (run from `frontend/`)
- `npx vitest run tests/unit/ask-store.test.ts tests/unit/ask-session-stream.test.tsx tests/unit/BreadcrumbWorkspace.test.tsx tests/unit/PlanningPanel.test.tsx --pool forks --poolOptions.forks.minForks=1 --poolOptions.forks.maxForks=1`
- `npx vitest run tests/unit --pool forks --poolOptions.forks.minForks=1 --poolOptions.forks.maxForks=1`

### Current frontend scope boundary

- Manual packet creation UI is still intentionally deferred
- Packet cards live in a dedicated AskPanel section, not inline with the message stream
- Backend remains the source of truth for packet mutation conflicts that cannot be derived cheaply from client state
