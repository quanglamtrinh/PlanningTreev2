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
| `initial_sha` | string or null | Baseline content hash at execution start |
| `head_sha` | string or null | Content hash after execution completes |
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
     "initial_sha": "<content-hash>",
     "head_sha": null,
     "started_at": "<ISO-now>",
     "completed_at": null
   }
   ```

3. **Update node status** in `tree.json`: set `status = "executing"`

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

Until git integration is implemented, SHAs are content-based hashes:

- **initial_sha**: SHA-256 of `frame.md + spec.md` content at Finish Task time
- **head_sha**: SHA-256 of workspace content after execution completes (or same content hash if execution made no file changes)

Format: `sha256:<hex-digest>` (prefix distinguishes from future git SHAs which will be plain hex).

SHA computation is a pure function: `compute_content_sha(node_dir: Path) -> str`.

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
