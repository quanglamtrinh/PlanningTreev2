# Thread State Model

Status: active spec (updated through Phase 7). Defines the shipped multi-thread architecture and lifecycle rules for task and review nodes.

## Thread Roles

Each session is keyed by `(project_id, node_id, thread_role)`.

| Role | Node kinds | Purpose | Creation source |
|------|------------|---------|-----------------|
| `audit` | task, review | Canonical lineage source for the node; local review chat; package audit; automated review rollup | Root task: `start_thread()`; review node: `fork(parent.audit)`; child task: `fork(review.audit)` when review ancestry exists |
| `ask_planning` | task only | Working shaping discussion for frame, clarify, and spec | `fork(task.audit)` |
| `execution` | task only | Automated implementation run from a confirmed spec | `fork(task.audit)` |

Review nodes use only `audit`. They never expose `ask_planning` or `execution`.

## Thread Role Enum

```ts
type ThreadRole = "audit" | "ask_planning" | "execution"
```

Python uses the same literal string set.

## Storage Layout

Task nodes:

```text
.planningtree/chat/{node_id}/audit.json
.planningtree/chat/{node_id}/ask_planning.json
.planningtree/chat/{node_id}/execution.json
```

Review nodes:

```text
.planningtree/chat/{review_node_id}/audit.json
```

Legacy single-file task sessions still migrate lazily to `ask_planning.json` on first read. Legacy review-node `integration.json` still migrates lazily to `audit.json` for historical data only.

### Session Schema

```json
{
  "thread_id": "codex-thread-id-or-null",
  "thread_role": "audit",
  "forked_from_thread_id": "upstream-thread-id-or-null",
  "forked_from_node_id": "upstream-node-id-or-null",
  "forked_from_role": "audit-or-null",
  "fork_reason": "root_bootstrap | ask_bootstrap | execution_bootstrap | review_bootstrap | child_activation | audit_lazy_bootstrap | legacy_resumed",
  "lineage_root_thread_id": "root-audit-thread-id-or-null",
  "active_turn_id": null,
  "messages": [],
  "created_at": "ISO",
  "updated_at": "ISO"
}
```

`messages` are local session history for UI/state tracking. They are not replayed into Codex threads and do not participate in fork inheritance.

## Lineage Model

### Root task audit

- `root.audit` is the only canonical task thread created with `start_thread()`.
- It is bootstrapped lazily on first access through `ThreadLineageService`.

### Task ask/planning

- `ask_planning` is created lazily on the first ask interaction.
- It is always `fork(task.audit)`.
- New `ask_planning` threads carry the superset shaping tool set needed for frame/spec/clarify generation.

### Execution

- `execution` is created only when Finish Task starts.
- It is always `fork(task.audit)`.
- Execution remains automated and user read-only.

### Review audit

- `review.audit` is the canonical review thread in v1.
- It is created from `fork(parent.audit)` after split persistence or rebuilt from that ancestor later if the app-server thread is missing.

### Child task audit

- When a child has review ancestry, `child.audit` is created from `fork(review.audit)`.
- If a node predates full lineage or has no review ancestry yet, `ThreadLineageService` may preserve or create truthful legacy/bootstrap sessions such as `legacy_resumed` or `audit_lazy_bootstrap` rather than inventing fake ancestry.

## Workflow-Boundary Context Injection

Canonical artifacts live in local storage and are injected only at workflow boundaries. They are not synthesized into chat sessions as seed messages.

### Ask planning

- Normal shaping chat uses `build_chat_prompt(...)`.
- For newly activated child tasks, child assignment and prior checkpoint context are injected from storage on the first successful `ask_planning` turn while the activation boundary is open.

### Execution

- Execution prompt assembly loads the confirmed frame and spec from storage.
- Execution never depends on synthetic session messages for canonical artifact delivery.

### Local review

- After execution completes, the first successful task-audit turn while local review is open uses `build_local_review_prompt(...)`.
- Boundary markers live in `execution_state.json`.

### Review rollup

- When rollup starts in `review.audit`, `build_rollup_prompt_from_storage(...)` injects parent context, split package context, and accepted checkpoints from storage.
- Review-node audit is automated and read-only to users.

### Package audit

- After an accepted rollup package is written to the parent audit, the first successful parent-audit turn while package review is open uses `build_package_review_prompt(...)`.
- Boundary markers live in `review_state.json`.

## Local Session Annotations

Some local-only audit messages remain valid and are not part of the retired seed mechanism:

- confirmed frame audit record
- confirmed spec audit record
- accepted rollup package record

These records exist for UI visibility and gating. They do not drive fork inheritance and are never replayed into Codex threads.

## Read-Only Rules

| Thread role | User write access |
|-------------|-------------------|
| `ask_planning` | Writable until Finish Task freezes shaping |
| `execution` | Never writable by user |
| `audit` on task nodes | Writable only during local review or package audit |
| `audit` on review nodes | Never writable by user |

Task-node audit becomes writable in exactly two cases:

1. Local review: this node's own execution completed.
2. Package audit: this node's review node has an accepted rollup package and that package record exists in the parent audit session.

## Recovery Rules

`ThreadLineageService` is the only owner of rebuild/recovery behavior.

- Lost `ask_planning` and `execution` threads rebuild by re-forking from the current node audit.
- Lost `review.audit` rebuilds by re-forking from `parent.audit`.
- Lost `child.audit` rebuilds by re-forking from `review.audit`.
- Lost `root.audit` reboots with `start_thread()`.
- Recovery never replays seed messages. It relies on lineage plus storage-backed prompt injection at the next workflow boundary.

## SSE and API Surface

Each thread role has its own SSE stream key: `(project_id, node_id, thread_role)`.

Chat endpoints accept `thread_role`:

```text
GET  /v1/projects/{pid}/nodes/{nid}/chat/session?thread_role=ask_planning
POST /v1/projects/{pid}/nodes/{nid}/chat/message?thread_role=ask_planning
GET  /v1/projects/{pid}/nodes/{nid}/chat/events?thread_role=ask_planning
POST /v1/projects/{pid}/nodes/{nid}/chat/reset?thread_role=ask_planning
```

Default remains `ask_planning`.

## Invariants

1. `root.audit` is the only task audit created with `start_thread()`.
2. New `ask_planning` and `execution` sessions are created by forking the node's `audit`.
3. Review nodes use `audit` rather than a dedicated `integration` thread.
4. Child tasks with review ancestry fork from `review.audit`.
5. Canonical artifacts are persisted to local storage before the downstream workflow boundary that consumes them.
6. Prompt builders, not seed insertion, deliver canonical storage-backed context at workflow boundaries.
7. No production service outside `ThreadLineageService` owns raw thread start/resume recovery logic.
8. Lost app-server threads rebuild from lineage and storage; canonical state is never recovered from Codex thread history.
