# Project CRUD

## Routes

- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{project_id}/snapshot`
- `GET /v1/projects/{project_id}/split-status`
- `POST /v1/projects/{project_id}/reset-to-root`
- `DELETE /v1/projects/{project_id}`

## Creation Rules

- Request body: `{ name, root_goal }`
- Create `<base_workspace_root>/<slugified-name>` for the project workspace.
- Resolve slug collisions with numeric suffixes: `-2`, `-3`, and so on.
- Create only `meta.json` and `tree.json`.
- `split_state.json` is created lazily on the first split run.
- Create the root tree entry inline with:
  `title = name`, `description = root_goal`, `status = draft`, `node_kind = "root"`, `depth = 0`, `display_order = 0`, `hierarchical_number = "1"`.
- Set `active_node_id` to the root node id.
- New projects persist `schema_version = 6`.

## Listing Rules

- `GET /v1/projects` reads only `meta.json`.
- The frontend uses the list to populate the project selector.
- If the persisted active project id is missing or stale, the frontend should auto-load the newest listed project instead of leaving the graph empty.

## Compatibility Rules

- There is no migration path for legacy project storage.
- Older project layouts must return `409 legacy_project_unsupported`.
