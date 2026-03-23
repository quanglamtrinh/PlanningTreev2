# Thread State Model

Status: spec (Phase 1 artifact). Defines the multi-thread architecture for node lifecycle.

## Thread Roles

Each task node can have up to three threads. Thread role is the primary key alongside `(project_id, node_id)`.

| Role | Purpose | Created when |
|------|---------|-------------|
| `ask_planning` | Working discussion for shaping (frame, clarify, spec) | When node reaches its turn |
| `execution` | Automated Codex code generation from confirmed spec | On Finish Task |
| `audit` | Official record (two-phase: seed context at creation, canonical artifacts after shaping); local review chat post-execution; package audit after rollup | When node reaches its turn |

Review nodes (`node_kind: review`) have a dedicated `integration` thread for agent-based integration rollup review. They do not use the standard three-role model. See `review-node-checkpoint.md`.

## Thread Role Enum

```
ThreadRole = "audit" | "ask_planning" | "execution" | "integration"
```

- `audit`, `ask_planning`, `execution`: used by task nodes
- `integration`: used by review nodes only (for agent-based rollup review)

Python: literal string union. TypeScript: `type ThreadRole = 'audit' | 'ask_planning' | 'execution' | 'integration'`.

## Storage Layout

### Current (single thread per node)

```
.planningtree/chat/{node_id}.json
```

### Target (one file per thread role)

Task nodes:
```
.planningtree/chat/{node_id}/audit.json
.planningtree/chat/{node_id}/ask_planning.json
.planningtree/chat/{node_id}/execution.json
```

Review nodes:
```
.planningtree/chat/{review_node_id}/integration.json
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

Audit is a **two-phase thread**:

**Phase 1 — Creation seed (when node reaches its turn):**

At creation time, audit receives only the context that exists at that moment:
- Split item for this node (title + objective from parent's split payload)
- Checkpoint context: latest accepted summary + SHA from review node
- Parent context needed for the node to begin shaping

At this point, the node's own confirmed frame and spec **do not exist yet** (the node hasn't been shaped). Audit does not contain them.

**Phase 2 — Canonical artifact snapshots (after shaping completes):**

When `confirm_frame()` succeeds in `ask_planning`, a snapshot of the confirmed frame is **appended** to audit as a canonical record message.

When `confirm_spec()` succeeds, a snapshot of the confirmed spec is **appended** to audit as a canonical record message.

These appends happen via service-level side effects (not user action). They are write-once: each artifact snapshot is appended exactly once.

**Phase 3 — Local review (after execution completes):**

Audit opens for user + agent chat to perform local review. See Read-Only Rules below.

**Phase 4 — Package audit (after rollup review from review node):**

If this node is a parent that was split, after its review node completes integration rollup, the accepted rollup package (summary + SHA) is written to this node's audit. The parent then reviews whether the package satisfies its own frame and split rationale.

Before execution completes, audit is **read-only** from the user's perspective.

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

### audit seed (two-phase)

**At creation time** (seed messages with `role: system`):
- Split item for this node (title + objective from parent's split payload)
- Checkpoint context: latest accepted summary + SHA from review node
- Parent chain context (ancestor prompts)

These are written once at creation and are immutable.

**After shaping** (canonical record messages, appended by service-level side effects):
- Confirmed frame content — appended when `confirm_frame()` succeeds
- Confirmed spec content — appended when `confirm_spec()` succeeds

Each canonical artifact is appended exactly once. They are also immutable after being written.

**After rollup** (for parent nodes that were split):
- Accepted rollup package (summary + SHA) from the review node — appended when `accept_rollup_review()` completes

### integration seed (review nodes only)

System prompt for the review node's integration thread:
- Parent's confirmed frame and split rationale
- All checkpoint summaries and SHAs (K0, K1, ...)
- All accepted local review summaries from child nodes
- Goal: detect integration gaps, conflicts, cross-child mismatches
- Output: rollup summary + final subtree SHA

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
5. `audit` creation seed messages are immutable. Canonical artifact snapshots (frame, spec) are appended once each after shaping. Post-execution chat messages are appended during local review.
6. Read-only enforcement is checked at service level (`ChatService`), not storage level.
7. Review nodes have only the `integration` thread role. They do not use `audit`, `ask_planning`, or `execution`.
8. `integration` thread is created lazily when rollup review begins (all siblings accepted).
