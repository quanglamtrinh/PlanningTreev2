# Thread State Model

Status: spec (Phase 1 artifact). Defines the multi-thread architecture for node lifecycle.

## Thread Roles

Each task node can have up to three threads. Thread role is the primary key alongside `(project_id, node_id)`.

| Role | Purpose | Created when |
|------|---------|-------------|
| `ask_planning` | Working discussion for shaping (frame, clarify, spec) | When node reaches its turn |
| `execution` | Automated Codex code generation from confirmed spec | On Finish Task |
| `audit` | Official record pre-execution; local review chat post-execution | When node reaches its turn |

Review nodes (`node_kind: review`) do not have threads. They use `review_state.json` for checkpoint/rollup state.

## Thread Role Enum

```
ThreadRole = "audit" | "ask_planning" | "execution"
```

Python: literal string union. TypeScript: `type ThreadRole = 'audit' | 'ask_planning' | 'execution'`.

## Storage Layout

### Current (single thread per node)

```
.planningtree/chat/{node_id}.json
```

### Target (one file per thread role)

```
.planningtree/chat/{node_id}/audit.json
.planningtree/chat/{node_id}/ask_planning.json
.planningtree/chat/{node_id}/execution.json
```

Each file follows the existing `ChatSession` schema with an added `thread_role` field:

```json
{
  "thread_id": "codex-thread-id-or-null",
  "thread_role": "ask_planning",
  "active_turn_id": null,
  "messages": [],
  "created_at": "ISO",
  "updated_at": "ISO"
}
```

### Migration Rule

On first read of `chat/{node_id}`:

1. If flat file `chat/{node_id}.json` exists AND directory `chat/{node_id}/` does not exist:
   - Create directory `chat/{node_id}/`
   - Move `chat/{node_id}.json` to `chat/{node_id}/ask_planning.json`
   - Add `"thread_role": "ask_planning"` to the migrated session
2. If both exist (partial migration), prefer the directory version.
3. If neither exists, return default empty session for the requested role.

Migration is lazy (on first access), not eager (no startup scan).

## Thread Creation Timing

### ask_planning

Created when the node "reaches its turn":
- **First child after split**: immediately (node gets `status: ready`)
- **Later sequential siblings**: lazily, after previous sibling's local review is accepted and checkpoint K(N) is written (see `lazy-sibling-creation.md`)

`ask_planning` is the default thread. All existing chat behavior (BreadcrumbChatView "Ask" tab) maps to this role.

### audit

Created at the same time as `ask_planning` (when node reaches its turn).

Before execution completes, audit is **not a chat room**. It holds canonical context:
- The node's split item (from parent's split payload)
- The latest accepted summary + SHA from the relevant checkpoint
- The node's confirmed frame
- The node's confirmed spec

These are written as system-level seed messages at creation time, not user messages.

### execution

Created only when user clicks **Finish Task** (see `execution-state-model.md`).

Execution thread uses an automated Codex prompt (not interactive chat). The thread runs a background job that generates code from the confirmed spec. User monitors output in read-only mode.

## Read-Only Rules

| Thread Role | Read-only when | Writable when |
|-------------|---------------|---------------|
| `ask_planning` | `execution_state` exists on node (Finish Task was clicked) | Before Finish Task |
| `execution` | `execution_state.status == completed` | During execution (`status == executing`) — but only Codex writes, not user |
| `audit` | `execution_state` is null OR `execution_state.status != completed` | After execution completes (`status == completed`) |

"Read-only" means:
- `create_message()` raises `ThreadReadOnly` error
- UI disables ComposerBar
- Existing messages remain visible

For `execution` thread specifically: user never writes directly. Codex writes during execution. After completion, the thread is read-only for everyone.

## Thread Seeding Context

### ask_planning seed

System prompt includes:
- Project name and root goal
- Parent chain prompts (ancestor context)
- Node title and description
- Current node prompt (compact format)
- Prior sibling summaries (if any, from checkpoint)

This matches the existing `build_chat_prompt()` pattern in `chat_prompt_builder.py`.

### audit seed

Initial messages (not system prompt, but seed messages with `role: system`):
- Split item for this node (title + objective from parent's split payload)
- Checkpoint context: latest accepted summary + SHA from review node
- Confirmed frame content (snapshot from `frame.meta.json.confirmed_content`)
- Confirmed spec content (from `spec.md`)

These are written once at audit creation time and are immutable.

### execution seed

System prompt for automated Codex execution:
- "You are executing a confirmed task spec. Implement the following spec."
- Full confirmed spec content
- Confirmed frame content for context
- Project workspace root as `cwd`
- No interactive tools — Codex works autonomously

## SSE Broker Key

Current: `(project_id, node_id)`
Target: `(project_id, node_id, thread_role)`

Each thread role gets its own SSE event stream. The frontend subscribes to the active tab's stream.

## API Surface Changes

All chat endpoints gain `thread_role` query parameter:

```
GET  /v1/projects/{pid}/nodes/{nid}/chat/session?thread_role=ask_planning
POST /v1/projects/{pid}/nodes/{nid}/chat/message?thread_role=ask_planning
GET  /v1/projects/{pid}/nodes/{nid}/chat/events?thread_role=ask_planning
POST /v1/projects/{pid}/nodes/{nid}/chat/reset?thread_role=ask_planning
```

Default value: `ask_planning` (backward compatible with existing callers).

## Invariants

1. A node has at most one session per thread role.
2. Thread role is immutable once set on a session.
3. `ask_planning` always exists if the node has reached its turn.
4. `execution` only exists after Finish Task.
5. `audit` seed messages are immutable; only post-execution chat messages are appended.
6. Read-only enforcement is checked at service level (`ChatService`), not storage level.
