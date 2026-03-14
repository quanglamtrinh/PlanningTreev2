# Feature Migration Queue

Version: 0.2.0-phase3
Last updated: 2026-03-08

## Phase 3 Queue

### M01 - Bootstrap + Workspace Setup

- Implement `GET /v1/bootstrap/status`, `GET /v1/settings/workspace`, and `PATCH /v1/settings/workspace`.
- Validate workspace roots as existing writable directories before persisting.
- Frontend shows `WorkspaceSetup` on fresh install and can update the stored path later from the graph shell.

### M02 - Project CRUD

- Implement project listing from `meta.json`.
- Implement project creation with `root_goal`, root node initialization, workspace folder creation, and slug collision handling.
- Implement snapshot loading from `state.json`.

### M03 - Node CRUD + Active Node Persistence

- Implement child creation, title/description updates, and `PATCH /v1/projects/{project_id}/active-node`.
- Persist `active_node_id` in the snapshot and use it as the frontend selection source of truth.
- Freeze `done` nodes and superseded nodes for edits and child creation.

### M04 - Completion + Unlock Cascade

- Implement `POST /v1/projects/{project_id}/nodes/{node_id}/complete`.
- Enforce leaf-only completion for `ready` and `in_progress` nodes.
- Unlock the next active sibling and cascade ancestor auto-close when all active children are done.

### M05 - Graph Workspace UI

- Rebuild the graph shell in `PlanningTreeMain` with the `PlanningTreeCodex` visual language.
- Keep the legacy top bar, theme switcher, graph shell, node card treatment, floating detail panel, and fullscreen graph affordance at high fidelity.
- Remove gate, rollback, version, audit, preview, and SSE UI.

### M06 - Breadcrumb Placeholder

- Add route `/projects/:projectId/nodes/:nodeId/chat`.
- Recreate the legacy breadcrumb shell, ancestry trail, left tab rail, and content panel as a read-only placeholder.
- Keep split, chat, and Mark Done behaviors deferred.
