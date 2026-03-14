# Core Graph

## Goal

Deliver the first usable rebuild slice: bootstrap a local workspace, create projects, manage a planning tree, and render that tree in a high-fidelity legacy-style graph workspace.

## Shared Types

- `Project`: `id`, `name`, `root_goal`, `base_workspace_root`, `project_workspace_root`, `created_at`, `updated_at`
- `ProjectSummary`: `id`, `name`, `root_goal`, `base_workspace_root`, `project_workspace_root`, `created_at`, `updated_at`
- `Node` (public snapshot): `node_id`, `parent_id`, `child_ids`, `title`, `description`, `status`, `phase`, `planning_mode`, `depth`, `display_order`, `hierarchical_number`, `split_metadata`, `chat_session_id`, `node_kind`, `is_superseded`, `created_at`
- `TreeState` (public snapshot): `root_node_id`, `active_node_id`, `node_registry`
- `Snapshot`: `schema_version`, `project`, `tree_state`, `updated_at`

## Status Model

`locked | draft | ready | in_progress | done`

Allowed transitions:

- `locked -> ready` through sibling unlock
- `ready -> draft` when a leaf gains its first child
- `ready -> in_progress` reserved for Phase 4
- `ready -> done` through completion
- `in_progress -> done` through completion
- `done` is terminal

## Storage Shape

`tree.json`

```json
{
  "schema_version": 5,
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

Per-node content lives under:

```text
nodes/{node_id}/task.md
nodes/{node_id}/briefing.md
nodes/{node_id}/spec.md
nodes/{node_id}/state.yaml
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

## Tree Rules

- `node_index` is stored as a dict on disk for fast lookup.
- Public snapshots still expose `node_registry` as an array for frontend compatibility.
- "Active children" means `node_kind !== "superseded"`.
- All traversal logic must operate on active children only.
- `done` nodes are frozen: no edits and no child creation.

## Acceptance

- A fresh install can configure a workspace root and create a project.
- The user can create child nodes, edit node content, reload, and keep selection state.
- The completion endpoint enforces progression and unlock rules without any gate-era concepts.
