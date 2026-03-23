# Execution State Model

Status: spec (Phase 1 artifact). Defines the execution lifecycle, Finish Task semantics, and SHA tracking.

## Execution State Structure

Per-node structure stored in `execution_state.json` within the node's working directory.

```json
{
  "status": "idle",
  "initial_sha": null,
  "head_sha": null,
  "started_at": null,
  "completed_at": null
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string enum | Current execution lifecycle phase |
| `initial_sha` | string or null | Workspace/subtree state SHA inherited from the latest checkpoint when this node's turn began |
| `head_sha` | string or null | Workspace/subtree state SHA after execution completes |
| `started_at` | ISO string or null | Timestamp when Finish Task was clicked |
| `completed_at` | ISO string or null | Timestamp when execution finished |

### Status Enum

```
ExecutionStatus = "idle" | "executing" | "completed" | "review_pending" | "review_accepted"
```

| Status | Meaning |
|--------|---------|
| `idle` | Default. Execution has not started. |
| `executing` | Finish Task clicked. Codex is running automated execution. |
| `completed` | Codex execution finished. Audit thread opens for local review. |
| `review_pending` | Local review started in audit thread. |
| `review_accepted` | Local review accepted. Summary + SHA handed to review node. |

State transitions are strictly forward: `idle -> executing -> completed -> review_pending -> review_accepted`. No backward transitions.

## Storage

File: `{workspace_root}/{project_name}/.planningtree/{node_name}/execution_state.json`

Follows the same directory as other node artifacts (`frame.md`, `frame.meta.json`, etc.).

When the file does not exist, the node has no execution state (equivalent to `status: idle`). The file is created on Finish Task.

## Finish Task

### Preconditions

All must be true:

1. **Spec confirmed**: `spec.meta.json` has `confirmed_at` set (non-null)
2. **Node is leaf**: `child_ids` is empty (node has not been split)
3. **Node status**: `ready` or `in_progress`
4. **No active execution**: `execution_state.json` does not exist or `status == idle`

If any precondition fails, return `400` with specific error message identifying which condition failed.

### Effects (atomic)

When Finish Task is triggered:

1. **Create execution thread** via Codex `start_thread()`:
   - `base_instructions`: automated execution prompt with confirmed spec content
   - `cwd`: project workspace root
   - No dynamic tools (Codex works autonomously)

2. **Write `execution_state.json`**:
   ```json
   {
     "status": "executing",
     "initial_sha": "<workspace-sha-from-checkpoint>",
     "head_sha": null,
     "started_at": "<ISO-now>",
     "completed_at": null
   }
   ```
   `initial_sha` is the workspace/subtree state SHA from the latest checkpoint of the parent's review node. For the first child, this is K0's SHA. For sibling N, this is K(N-1)'s SHA. This is the same SHA type used in checkpoints and handoff.

3. **Update node status** in `tree.json`: set `status = "in_progress"` (node.status stays coarse — see Status Model below)

4. **Create execution chat session**: `chat/{node_id}/execution.json` with the new Codex `thread_id`

5. **Start background execution job** (same pattern as `_run_background_split` in `split_service.py`):
   - Run Codex turn with the confirmed spec as the prompt
   - Stream output to execution chat session (for monitoring)
   - On completion, call `complete_execution()`

6. **Freeze shaping**: the existence of `execution_state.json` signals that shaping tabs (frame, clarify, spec) are read-only. No separate flag needed — service checks `execution_state` existence.

### Shaping Freeze

When `execution_state.json` exists (any status):
- `save_frame()`, `save_spec()` -> reject with `ShapingFrozen` error
- `confirm_frame()`, `confirm_clarify()`, `confirm_spec()` -> reject with `ShapingFrozen` error
- UI shows all shaping tabs as read-only with "Frozen for execution" banner
- `generate_frame()`, `generate_clarify()`, `generate_spec()` -> reject with `ShapingFrozen` error

## Execution Completion

Called automatically when the Codex background job finishes (not user-triggered).

### Effects

1. **Update `execution_state.json`**:
   ```json
   {
     "status": "completed",
     "initial_sha": "<unchanged>",
     "head_sha": "<new-content-hash>",
     "started_at": "<unchanged>",
     "completed_at": "<ISO-now>"
   }
   ```

2. **Publish SSE event**: `execution_completed` event to `(project_id, node_id, execution)` stream

3. **Audit thread becomes writable**: read-only check in `ChatService` now passes for `audit` role (since `status == completed`)

### Error Handling

If Codex execution fails:
- Set `execution_state.status = "completed"` (execution attempt is done, even if it failed)
- Record the error in the execution chat session's last message (`status: error`)
- Do NOT set `head_sha` (remains null — signals failed execution)
- Audit thread still opens for review (user decides whether to accept or not)

## SHA Strategy

**SHA always means workspace/subtree state SHA.** It represents the state of the workspace (code, files) at a point in time, not the state of shaping artifacts.

### Consistent SHA meaning across the system

| Context | SHA meaning |
|---------|------------|
| `execution_state.initial_sha` | Workspace state when this node's turn began (inherited from checkpoint) |
| `execution_state.head_sha` | Workspace state after this node's execution completed |
| Checkpoint K(N) SHA | Workspace state after sibling N's execution + local review |
| Rollup SHA | Final workspace state after entire subtree completed |
| Upward handoff SHA | Same as rollup SHA |

All SHAs are the same type: workspace/subtree state. This ensures local review (initial_sha vs head_sha), checkpoint chaining, and sibling seeding all use a single coherent anchor.

### Placeholder implementation (before git integration)

Until real git integration:
- SHA is computed as SHA-256 of the workspace directory tree (file paths + contents)
- Format: `sha256:<hex-digest>`
- Computation: `compute_workspace_sha(workspace_root: Path) -> str`

After git integration:
- SHA becomes the actual git commit SHA
- Format: plain 40-char hex (standard git SHA)
- The schema field stays the same; only the value format changes

### What SHA is NOT

SHA is not a hash of shaping artifacts (frame.md + spec.md). If artifact fingerprinting is needed later, it should use a separate field name (e.g., `artifact_fingerprint`), not the `sha` fields.

## Status Model

There are two separate status systems. They do not overlap.

### node.status (coarse workflow/tree state)

```
"locked" | "draft" | "ready" | "in_progress" | "done"
```

`node.status` describes where the node is in the overall tree lifecycle. It does NOT have `executing` or `in_review` values. Those are tracked by `execution_state.status`.

| node.status | Meaning |
|-------------|---------|
| `locked` | Waiting for predecessor or parent |
| `draft` | Parent has been split (children exist) |
| `ready` | Node can begin shaping |
| `in_progress` | User has started working on this node (chat or shaping) |
| `done` | Node work is complete (all reviews accepted) |

Finish Task sets `node.status = "in_progress"` (if not already). It does NOT set a special execution status on node.status.

### execution_state.status (execution/review lifecycle)

```
"idle" | "executing" | "completed" | "review_pending" | "review_accepted"
```

`execution_state.status` is the **sole source of truth** for execution and review lifecycle. UI badges ("Executing", "In Review", "Accepted") read from this field, not from `node.status`.

### When node.status transitions to "done"

`node.status` becomes `"done"` when `execution_state.status` reaches `"review_accepted"`. This is the only path to `done` for task nodes that go through execution.

## Detail State Extensions

`GET /v1/projects/{pid}/nodes/{nid}/detail-state` response gains:

```json
{
  "workflow": { "...existing fields..." },
  "execution_started": false,
  "execution_completed": false,
  "shaping_frozen": false,
  "can_finish_task": true,
  "execution_status": null
}
```

| Field | Type | Derivation |
|-------|------|-----------|
| `execution_started` | bool | `execution_state.json` exists and `status != idle` |
| `execution_completed` | bool | `execution_state.status == completed` or later |
| `shaping_frozen` | bool | `execution_state.json` exists |
| `can_finish_task` | bool | spec confirmed AND leaf AND status ready/in_progress AND no execution_state |
| `execution_status` | string or null | `execution_state.status` or null if no file |

## Invariants

1. `execution_state.json` is created exactly once per node (on Finish Task). It is never deleted.
2. Status transitions are strictly forward. No rollback.
3. `initial_sha` is set at creation and never changes.
4. `head_sha` is set only on completion.
5. Shaping freeze is permanent once execution starts.
6. `execution_state.json` existence is the canonical signal for "this node has entered execution phase".
