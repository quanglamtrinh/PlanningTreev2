# Type Contracts v2

Status: spec (Phase 1 artifact). Defines all new and modified types for the thread/review model.

## New Enums and Unions

### ThreadRole

```typescript
// TypeScript
type ThreadRole = 'audit' | 'ask_planning' | 'execution' | 'integration'
```

- `audit`, `ask_planning`, `execution`: used by task nodes
- `integration`: used by review nodes only (for agent-based integration rollup)

```python
# Python (typing)
ThreadRole = Literal["audit", "ask_planning", "execution", "integration"]
```

### Extended NodeKind

```typescript
// TypeScript — was: 'root' | 'original' | 'superseded'
type NodeKind = 'root' | 'original' | 'superseded' | 'review'
```

```python
# Python — _ALLOWED_NODE_KINDS in project_store.py
_ALLOWED_NODE_KINDS = {"root", "original", "superseded", "review"}
```

### NodeStatus (unchanged)

`node.status` stays coarse. It does NOT gain `executing` or `in_review` values. Execution/review lifecycle is tracked solely by `execution_state.status`.

```typescript
// TypeScript — unchanged
type NodeStatus = 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
```

```python
# Python — _ALLOWED_NODE_STATUSES in project_store.py — unchanged
_ALLOWED_NODE_STATUSES = {"locked", "draft", "ready", "in_progress", "done"}
```

UI badges for execution/review state ("Executing", "In Review", "Accepted") are derived from `execution_state.status`, not from `node.status`. See `execution-state-model.md` for the Status Model section.

### ExecutionStatus

```typescript
type ExecutionStatus = 'idle' | 'executing' | 'completed' | 'review_pending' | 'review_accepted'
```

```python
ExecutionStatus = Literal["idle", "executing", "completed", "review_pending", "review_accepted"]
```

### RollupStatus

```typescript
type RollupStatus = 'pending' | 'ready' | 'accepted'
```

## New Structures

### ExecutionState

```typescript
interface ExecutionState {
  status: ExecutionStatus
  initial_sha: string | null
  head_sha: string | null
  started_at: string | null   // ISO datetime
  completed_at: string | null // ISO datetime
}
```

```python
# Python dict shape (not a dataclass — follows existing dict-based patterns)
{
    "status": str,         # ExecutionStatus
    "initial_sha": str | None,
    "head_sha": str | None,
    "started_at": str | None,
    "completed_at": str | None,
}
```

### CheckpointRecord

```typescript
interface CheckpointRecord {
  label: string             // "K0", "K1", ...
  sha: string
  summary: string | null    // null for K0
  source_node_id: string | null  // null for K0
  accepted_at: string       // ISO datetime
}
```

### RollupState

```typescript
interface RollupState {
  status: RollupStatus
  summary: string | null
  sha: string | null
  accepted_at: string | null
}
```

### PendingSibling

```typescript
interface PendingSibling {
  index: number                       // 1-based position in split order
  title: string
  objective: string
  materialized_node_id: string | null // null until activated
}
```

### ReviewState

```typescript
interface ReviewState {
  checkpoints: CheckpointRecord[]
  rollup: RollupState
  pending_siblings: PendingSibling[]
}
```

## Modified Structures

### NodeRecord (extended)

```typescript
// Existing fields remain unchanged. New optional fields added:
interface NodeRecord {
  // ... existing fields ...
  node_id: string
  parent_id: string | null
  child_ids: string[]
  title: string
  description: string
  status: NodeStatus          // unchanged (coarse); execution lifecycle in execution_state
  node_kind: NodeKind         // extended with 'review'
  depth: number
  display_order: number
  hierarchical_number: string
  created_at: string
  workflow: NodeWorkflowSummary | null  // null for review nodes

  // NEW fields
  review_node_id?: string | null            // present on parent that has been split
  // Note: execution_state is NOT in NodeRecord / tree.json — it is loaded separately via detail-state
}
```

```python
# Python — _ALLOWED_NODE_FIELDS in project_store.py
_ALLOWED_NODE_FIELDS = {
    "node_id",
    "parent_id",
    "child_ids",
    "title",
    "description",
    "status",           # coarse: locked/draft/ready/in_progress/done (unchanged)
    "node_kind",        # extended with "review"
    "depth",
    "display_order",
    "hierarchical_number",
    "created_at",
    # NEW
    "review_node_id",   # points to review node (on parent that was split)
}
```

Note: `execution_state` is stored in a separate file (`execution_state.json` in the node directory), NOT as a field in `tree.json`. This keeps snapshot payloads lean. Execution state is loaded on demand via `detail-state` endpoint.

### NodeWorkflowSummary (extended)

```typescript
// Existing fields remain. New fields added for detail-state response:
interface NodeWorkflowSummary {
  // Existing
  frame_confirmed: boolean
  active_step: 'frame' | 'clarify' | 'spec'
  spec_confirmed: boolean

  // NEW — execution awareness
  execution_started: boolean      // execution_state exists and status != idle
  execution_completed: boolean    // status in {completed, review_pending, review_accepted}
  shaping_frozen: boolean         // execution_state exists
  can_finish_task: boolean        // spec confirmed AND leaf AND ready/in_progress AND no execution
  execution_status: ExecutionStatus | null  // raw status or null
}
```

Note: for review nodes, `workflow` is `null` — they don't have shaping state.

### ChatSession (extended)

```typescript
interface ChatSession {
  thread_id: string | null
  thread_role: ThreadRole       // NEW
  active_turn_id: string | null
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}
```

### ReviewGraphNodeData (updated)

```typescript
// Was: synthetic overlay data
// Now: real node data
type ReviewGraphNodeData = {
  nodeId: string                    // real node_id
  parentNodeId: string
  parentTitle: string
  parentHierarchicalNumber: string
  checkpointCount: number           // NEW: number of checkpoints
  rollupStatus: RollupStatus        // NEW: pending | ready | accepted
  pendingSiblingCount: number       // NEW: unmaterialized siblings remaining
}
```

## Snapshot Response Changes

The `node_registry` array in the snapshot response now includes review nodes alongside task nodes. Review nodes are identifiable by `node_kind: 'review'`.

```typescript
// GET /v1/projects/{pid}/snapshot response shape
interface SnapshotResponse {
  // ... existing fields ...
  tree_state: {
    root_node_id: string
    active_node_id: string | null
    node_registry: NodeRecord[]  // now includes review nodes
  }
}
```

Review nodes in `node_registry`:
- Have `node_kind: 'review'`
- Have `workflow: null`
- Have `review_node_id: undefined` (they ARE the review node, they don't HAVE one)
- Are NOT in any node's `child_ids`
- Can be found via `parent.review_node_id` where parent is the splitting node

## Detail State Response Changes

```typescript
// GET /v1/projects/{pid}/nodes/{nid}/detail-state response
interface DetailStateResponse {
  workflow: NodeWorkflowSummary | null  // null for review nodes
  // ... existing fields ...

  // NEW
  execution_started: boolean
  execution_completed: boolean
  shaping_frozen: boolean
  can_finish_task: boolean
  execution_status: ExecutionStatus | null
  audit_writable: boolean              // true when audit chat is writable (local review OR package audit)
  package_audit_ready: boolean         // true when review node rollup accepted + package appended
  review_status: RollupStatus | null   // for review nodes only
}
```

## API Parameter Changes

### Chat endpoints

All chat endpoints gain `thread_role` query parameter:

```typescript
// Query parameter
thread_role?: ThreadRole  // default: 'ask_planning'
```

### New endpoints

```typescript
// POST /v1/projects/{pid}/nodes/{nid}/finish-task
// Request: empty body
// Response: DetailStateResponse

// POST /v1/projects/{pid}/nodes/{nid}/accept-local-review
// Request: { summary: string }
// Response: { execution_state: ExecutionState, checkpoint: CheckpointRecord }

// POST /v1/projects/{pid}/nodes/{nid}/accept-rollup-review
// Request: { summary: string }
// Response: { rollup: RollupState }
```

## Backward Compatibility

All new fields on `NodeRecord` are optional with null/undefined defaults:
- `execution_state`: absent means no execution (equivalent to `status: idle`)
- `review_node_id`: absent means no split/no review node

Existing `tree.json` files load without errors. The `_ALLOWED_NODE_FIELDS` whitelist in `project_store.py` will silently drop unknown fields on save, so new fields must be added to the whitelist.

Existing `chat/{node_id}.json` files work unchanged — the `thread_role` field defaults to `ask_planning` on read, and migration to directory structure happens lazily.
