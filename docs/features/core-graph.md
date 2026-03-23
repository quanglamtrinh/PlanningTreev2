# Core Graph

## Goal

Deliver a graph-first slice: bootstrap a local workspace, create projects, manage a task tree, run AI split, and render the tree in the graph workspace.

## Shared Types

- `Project`: `id`, `name`, `root_goal`, `base_workspace_root`, `project_workspace_root`, `created_at`, `updated_at`
- `ProjectSummary`: `id`, `name`, `root_goal`, `base_workspace_root`, `project_workspace_root`, `created_at`, `updated_at`
- `Node` (public snapshot): `node_id`, `parent_id`, `child_ids`, `title`, `description`, `status`, `node_kind`, `depth`, `display_order`, `hierarchical_number`, `created_at`, `is_superseded`, `workflow`
- `TreeState` (public snapshot): `root_node_id`, `active_node_id`, `node_registry`
- `Snapshot`: `schema_version`, `project`, `tree_state`, `updated_at`

## Status Model

`locked | draft | ready | in_progress | done`

Allowed transitions:

- `locked -> ready` through sibling ordering rules
- `ready -> draft` when a leaf gains its first child
- `ready -> in_progress` reserved for future work
- `ready -> done` reserved for future work
- `in_progress -> done` reserved for future work

## Storage Shape

`tree.json`

```json
{
  "schema_version": 6,
  "project": {
    "id": "string",
    "name": "string",
    "root_goal": "string",
    "base_workspace_root": "string",
    "project_workspace_root": "string",
    "created_at": "ISO timestamp",
    "updated_at": "ISO timestamp"
  },
  "tree_state": {
    "root_node_id": "string",
    "active_node_id": "string | null",
    "node_index": {}
  },
  "updated_at": "ISO timestamp"
}
```

`meta.json`

```json
{
  "id": "string",
  "name": "string",
  "root_goal": "string",
  "base_workspace_root": "string",
  "project_workspace_root": "string",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp"
}
```

`split_state.json`

```json
{
  "thread_id": "string | null",
  "active_job": "object | null",
  "last_error": "object | null"
}
```

## Tree Rules

- `node_index` is stored as a dict on disk for fast lookup.
- Public snapshots expose `node_registry` as an array for frontend compatibility.
- `title` and `description` are stored inline in `tree.json`; there are no per-node content files.
- Split runtime state is stored separately in `split_state.json`; split results still materialize inline into `tree.json`.
- "Active children" means `node_kind !== "superseded"`.
- All traversal logic must operate on active children only.
- `done` nodes are frozen: no child creation.
- `workflow` is derived from node artifact metadata and currently exposes `frame_confirmed`, `active_step`, and `spec_confirmed` for graph action gating.

## Acceptance

- A fresh install can configure a workspace root and create a project.
- The user can create child nodes, edit node title/description, reload, and keep selection state.
- The user can split an eligible leaf node only after the node is workflow-ready (`frame_confirmed` and `active_step = spec`) and get inline child nodes back without opening breadcrumb.
- Reset-to-root collapses the tree back to its root node.
