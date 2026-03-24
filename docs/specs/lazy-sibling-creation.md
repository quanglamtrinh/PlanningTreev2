# Lazy Sibling Creation

Status: spec (Phase 1 artifact). Defines how sequential siblings are materialized one at a time after local review acceptance.

## Current Behavior

In `split_service.py`, `_materialize_split_payload` creates all children eagerly (lines 210-228):

```python
for index, subtask in enumerate(payload["subtasks"], start=1):
    child_node = {
        "status": "locked" if inherited_locked or index != 1 else "ready",
        ...
    }
    parent.setdefault("child_ids", []).append(child_id)
    snapshot["tree_state"]["node_index"][child_id] = child_node
```

All siblings are materialized at split time. First child gets `status: ready`, rest get `status: locked`.

## Target Behavior

Split creates **only the first child** plus a **review node**. Remaining siblings are stored as a **pending sibling manifest** in the review node's `review_state.json`.

### What split produces

1. **First child node**: `status: ready`, `node_kind: original`, added to `parent.child_ids`
2. **Review node**: `node_kind: review`, stored separately via `parent.review_node_id`
3. **Pending siblings manifest**: remaining subtasks stored in `review_state.json.pending_siblings`
4. **Checkpoint K0**: baseline checkpoint in `review_state.json.checkpoints`

### What split does NOT produce

- Second, third, ... child nodes are NOT created in `tree_state.node_index`
- No `locked` sibling nodes exist in the tree
- The tree only contains nodes that have "reached their turn"

## Pending Sibling Manifest

Stored in `review_state.json` under the review node:

```json
{
  "pending_siblings": [
    {
      "index": 2,
      "title": "Implement authentication middleware",
      "objective": "Full objective text from split payload...",
      "materialized_node_id": null
    },
    {
      "index": 3,
      "title": "Add rate limiting",
      "objective": "Full objective text from split payload...",
      "materialized_node_id": null
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `index` | int | 1-based position in the original split order (first child is index 1, already materialized) |
| `title` | string | Subtask title from split payload |
| `objective` | string | Full objective/description from split payload |
| `materialized_node_id` | string or null | Node ID once created, null while pending |

## Activation Trigger

A pending sibling is activated when ALL of the following are true:

1. The immediately preceding sibling has `execution_state.status == review_accepted`
2. A new checkpoint K(N) has been written to the review node
3. There exists a next entry in `pending_siblings` with `materialized_node_id == null`

This check runs automatically inside `accept_local_review()` in `ReviewService`.

## Activation Effect

When the next sibling is activated:

1. **Create sibling node** in `tree_state.node_index`:
   ```json
   {
     "node_id": "<new-uuid>",
     "parent_id": "<splitting-parent-id>",
     "child_ids": [],
     "title": "<from manifest>",
     "description": "<from manifest objective>",
     "status": "ready",
     "node_kind": "original",
     "depth": "<parent.depth + 1>",
     "display_order": "<index - 1>",
     "hierarchical_number": "<parent_hnum>.<index>",
     "created_at": "<ISO-now>"
   }
   ```

2. **Add to parent's child_ids**: append new `node_id` to `parent.child_ids`

3. **Update manifest**: set `materialized_node_id` to the new node's ID

4. **Create audit thread** (`chat/{node_id}/audit.json`):
   - Seed with latest checkpoint summary + SHA
   - Seed with this sibling's split item (title + objective)
   - Seed with parent's confirmed frame content

5. **Create ask_planning thread** (`chat/{node_id}/ask_planning.json`):
   - Seed with node context (same as existing `build_chat_prompt` pattern)
   - Include checkpoint context so the sibling knows what predecessors achieved

6. **Set as active node**: `snapshot.tree_state.active_node_id = new_node_id`

7. **Save snapshot**: persist all changes atomically

## Seeding from Checkpoint (not from stale split context)

This is the key difference from eager creation:

- **Old model**: sibling 1.B is created at split time from the parent's context. By the time 1.B starts, 1.A may have significantly changed the codebase. 1.B starts from stale context.
- **New model**: sibling 1.B is created only after 1.A's local review is accepted. 1.B's audit thread includes checkpoint K1 which contains 1.A's accepted summary and SHA. 1.B starts with current context.

## Backward Compatibility

- **Existing trees with all children already created**: remain valid. The system checks `pending_siblings` — if the field is absent or empty, no lazy activation occurs. Existing `locked` children continue to work as before.
- **New splits**: produce lazy siblings (first child + manifest). Only new splits after this feature is implemented use the lazy model.
- **No migration needed**: old trees don't have `review_state.json` or `review_node_id`. The absence of these fields means "legacy eager split" and the system falls back to existing behavior.

## Single-Child Split

If split produces only one subtask:
- Create the single child node with `status: ready`
- Create review node with empty `pending_siblings: []`
- Checkpoint K0 is still created
- After the single child's local review, rollup auto-triggers immediately (no more pending siblings)

## Display

### Graph Visualization

Pending siblings that haven't been materialized can be shown as "ghost nodes" in the graph:
- Semi-transparent card
- Label: "Waiting for {previous_sibling_hierarchical_number} review"
- Not clickable / not navigable
- Positioned in the expected sibling slot

Ghost nodes are derived from `pending_siblings` manifest data, not from `node_index`.

### Review Node Detail

The review node detail view shows:
- Checkpoint history (K0, K1, ...)
- Sibling progress: completed / active / pending counts
- Next sibling to activate (title + objective)

## Invariants

1. At most one sibling is `ready` or `in_progress` at any time within a sequential chain.
2. `pending_siblings` entries are processed in order. No skipping.
3. A materialized sibling's `materialized_node_id` is set exactly once and never changes.
4. The first child (index 1) is always materialized at split time.
5. Activation is triggered by `accept_local_review`, not by any other action.
6. If there are no `pending_siblings`, the chain is complete and rollup can proceed.
