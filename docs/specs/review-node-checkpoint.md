# Review Node and Checkpoint Model

Status: spec (updated through Phase 6). Defines review node identity, checkpoint chain, and rollup review.

## Review Node

A review node is a real persisted node in `tree_state.node_index` with `node_kind: review`.

### Identity

- `node_id`: standard UUID hex (same as task nodes)
- `node_kind`: `"review"` (new value added to `_ALLOWED_NODE_KINDS`)
- `parent_id`: the splitting parent's `node_id`
- `title`: `"Review"` (fixed)
- `description`: `"Review node for {parent_hierarchical_number} {parent_title}"`
- `status`: `"ready"` (fixed, review nodes don't have a status lifecycle)
- `depth`: `parent.depth + 1`

### Storage Position

Review nodes are stored **separately** from task children:

- Review node IS in `tree_state.node_index` (it is a real node)
- Review node is NOT in `parent.child_ids`
- Parent gains a `review_node_id: string | null` field pointing to the review node

This separation ensures that tree traversal logic (depth calculation, sibling ordering, locked ancestor checks) is not affected by review nodes.

### When Created

A review node is created during `_materialize_split_payload` in `split_service.py`, at the same time as the first child node.

### No Shaping Workflow

Review nodes do not go through the frame/clarify/spec workflow. They have no `frame.md`, `clarify.json`, or `spec.md`. The `workflow` summary for a review node is null/empty.

Review nodes DO have a canonical `audit` thread for agent-based rollup analysis (see Review Audit Thread section below).

The UI shows a dedicated checkpoint/rollup view for review nodes instead of the shaping NodeDetailCard.

## Checkpoint Model

### Storage

`review_state.json` is stored in the review node's working directory:

```
.planningtree/{review_node_name}/review_state.json
```

### Schema

```json
{
  "checkpoints": [
    {
      "label": "K0",
      "sha": "sha256:abc123...",
      "summary": null,
      "source_node_id": null,
      "accepted_at": "2026-03-23T10:00:00Z"
    }
  ],
  "rollup": {
    "status": "pending",
    "summary": null,
    "sha": null,
    "accepted_at": null
  },
  "pending_siblings": [
    {
      "index": 2,
      "title": "Sibling B title",
      "objective": "Sibling B objective text",
      "materialized_node_id": null
    },
    {
      "index": 3,
      "title": "Sibling C title",
      "objective": "Sibling C objective text",
      "materialized_node_id": null
    }
  ]
}
```

### Checkpoint Fields

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | `"K0"`, `"K1"`, `"K2"`, ... (sequential) |
| `sha` | string | Content SHA at this checkpoint |
| `summary` | string or null | Accepted summary from local review (null for K0) |
| `source_node_id` | string or null | Node whose local review produced this checkpoint (null for K0) |
| `accepted_at` | ISO string | When this checkpoint was created |

### Checkpoint Progression

```
K0 (split baseline)
  -> 1.A executes, local review accepted
K1 (after 1.A)
  -> 1.B executes, local review accepted
K2 (after 1.B)
  -> 1.C executes, local review accepted
K3 (after 1.C)
  -> rollup review
```

- **K0**: created at split time. SHA is the workspace/subtree state SHA at the moment of split. Summary is null.
- **K(N)**: created when sibling N's local review is accepted. SHA is sibling N's `head_sha` (workspace state after that sibling's execution). Summary is the accepted local review summary.

All SHAs here are workspace/subtree state SHAs — the same type used in `execution_state.initial_sha`, `execution_state.head_sha`, and upward handoff. See `execution-state-model.md` SHA Strategy for the consistent definition.

### Checkpoint as Sibling Seed

When a new sibling is activated (see `lazy-sibling-creation.md`), its audit thread is seeded with:
- The latest checkpoint's summary and SHA
- The sibling's split item (title + objective from `pending_siblings`)

This ensures each sibling starts from the latest accepted state, not stale split-time context.

## Three-Layer Review Model

Review happens at three distinct layers. Each layer has a different scope and purpose.

### Layer 1: Local Review (child audit)

- **Where**: in each child node's `audit` thread, after execution completes
- **Scope**: review that individual subtask's own work
- **Compares**: `initial_sha` (workspace state when child started) vs `head_sha` (workspace state after execution)
- **Outcome**: accepted summary + head_sha for this one child
- **Purpose**: "Did this subtask do what its spec said?"

### Layer 2: Integration Rollup (review node)

- **Where**: in the review node's `audit` thread
- **Scope**: review how all children fit together as a whole
- **Input**: all checkpoint summaries + SHAs (K0 through K(N)), all accepted local review summaries
- **Agent role**: detect conflicts between subtasks, overlap, missing glue, integration mismatches, ordering issues
- **Outcome**: rollup summary + final subtree SHA
- **Purpose**: "Do these pieces work together correctly?"

The review node has its own Codex thread (`audit` role — see `thread-state-model.md`) specifically for this agent-based analysis. This is NOT a standard ask/planning or execution thread. It is a specialized audit thread where the agent reasons across the set of child SHAs and summaries.

### Layer 3: Package Audit (parent audit)

- **Where**: in the parent node's `audit` thread, after rollup is accepted
- **Scope**: review the entire rollup package against the parent's original intent
- **Input**: accepted rollup summary + SHA from the review node
- **Question**: "Does this completed package satisfy my frame and split rationale?"
- **Outcome**: parent accepts or flags issues with the package
- **Purpose**: "Is the order I placed fulfilled correctly?"

### Naming Convention

To avoid confusion between "review" at different layers:

| Layer | Name | Location |
|-------|------|----------|
| Layer 1 | **Local review** | child audit thread |
| Layer 2 | **Integration rollup** | review node (audit thread) |
| Layer 3 | **Package audit** | parent audit thread |

## Review Audit Thread

Review nodes use a canonical `audit` thread (stored at `chat/{review_node_id}/audit.json`).

This thread is:
- Usually forked from `parent.audit` after split persistence and rebuilt lazily from lineage if missing later
- Used by a Codex agent to perform integration analysis
- NOT interactive chat — agent runs analysis, user reviews the output
- Read-only after rollup is accepted

The review audit thread receives rollup context via prompt-builder injection at rollup start:
- Parent task context
- Accepted checkpoint records (K0 through final)
- Split package context and accepted local review summaries from child nodes
- Workspace/subtree state at each checkpoint

The agent's job:
- Detect conflicts between subtask outputs
- Identify overlap or redundant work
- Flag missing integration glue
- Check that the realized subtree matches the split rationale
- Produce a rollup summary + final subtree SHA

## Rollup Review

### Rollup State

```json
{
  "status": "pending" | "ready" | "accepted",
  "summary": null,
  "sha": null,
  "accepted_at": null
}
```

| Status | Meaning |
|--------|---------|
| `pending` | Not all siblings have completed local review |
| `ready` | All siblings accepted; rollup review can begin |
| `accepted` | Rollup review completed; summary + SHA ready for upward handoff |

### Auto-Trigger

Rollup transitions from `pending` to `ready` **automatically** when:

1. `pending_siblings` has no remaining unmaterialized entries (all siblings created)
2. All materialized siblings have `execution_state.status == review_accepted`

This check runs inside `accept_local_review()` after updating the checkpoint. No user action needed.

### Rollup Review Process (Integration Rollup — Layer 2)

When rollup is `ready`:

1. Ensure the review node's `audit` thread exists (`chat/{review_node_id}/audit.json`)
2. Seed the thread with parent frame, split rationale, all checkpoint records, all accepted local review summaries
3. Run Codex agent in the review audit thread — agent performs automated analysis:
   - Detect conflicts, overlap, missing glue, integration mismatches
   - Compare realized subtree against parent's split rationale
4. Agent produces a rollup summary + final subtree SHA
5. Review node detail view shows the rollup summary for user review
6. User accepts or flags issues
7. On acceptance: `rollup.status = "accepted"`, `rollup.summary` and `rollup.sha` are set

### Upward Handoff (to Package Audit — Layer 3)

After rollup is accepted, the accepted package is written to the parent node's `audit` thread:

```json
{
  "summary": "Rollup summary text...",
  "sha": "sha256:final-subtree-sha",
  "review_node_id": "uuid-hex",
  "accepted_at": "ISO"
}
```

This is the compact handoff unit. The parent receives this, not raw child discussion.

The parent then performs **package audit** (Layer 3) in its own audit thread: reviewing whether the completed package satisfies the parent's frame and split rationale. See `thread-state-model.md` audit Phase 4.

## Graph Layout

### Current (synthetic overlay)

```typescript
const REVIEW_NODE_PREFIX = 'review::'
// buildReviewOverlayPositions generates review::{parentId} entries
```

### Target (real node data)

- `buildReviewOverlayPositions` reads `parent.review_node_id` from `node_registry` to find review nodes
- Uses the real review node's `node_id` instead of synthetic `review::` prefix
- `ReviewGraphNode.tsx` receives real node data with checkpoint count and rollup status
- Review node is positioned between parent and first child (existing Y-position logic)

### ReviewGraphNode Data

```typescript
type ReviewGraphNodeData = {
  nodeId: string           // real node_id (not synthetic)
  parentNodeId: string
  parentTitle: string
  parentHierarchicalNumber: string
  checkpointCount: number  // number of checkpoints (K0, K1, ...)
  rollupStatus: 'pending' | 'ready' | 'accepted'
}
```

## Node Registry Inclusion

Review nodes appear in `node_registry` (the public snapshot response) with `node_kind: review`. This allows the frontend to render them. However, they are **not** in any node's `child_ids`, so tree traversal in `TreeService` is unaffected.

`SnapshotViewService` must include review nodes when building `node_registry`:
- Scan `node_index` for entries with `node_kind: review`
- Include them in the output array alongside task nodes

## Invariants

1. A parent can have at most one review node (`review_node_id` is singular).
2. Review node is created exactly once per split (alongside the first child).
3. Checkpoints are append-only. No checkpoint is ever removed.
4. Rollup status transitions forward only: `pending -> ready -> accepted`.
5. Review node has no shaping workflow artifacts (no frame/clarify/spec).
6. Review node `status` is always `ready` (it does not go through locked/draft/in_progress/done).
7. `pending_siblings` entries are ordered by `index` and processed sequentially.
8. All SHAs in checkpoints and rollup are workspace/subtree state SHAs (same type as `execution_state` SHAs).
9. The review node uses `audit` rather than a dedicated `integration` thread.
10. Review at three layers: local review (child audit) -> integration rollup (review audit) -> package audit (parent audit).
