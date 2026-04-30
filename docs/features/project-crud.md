# Project CRUD

## Routes

- `GET /v4/projects`
- `POST /v4/projects/attach`
- `GET /v4/projects/{project_id}/snapshot`
- `GET /v4/projects/{project_id}/artifact-jobs/split/status`
- `POST /v4/projects/{project_id}/reset-to-root`
- `DELETE /v4/projects/{project_id}`

## Creation Rules

- Attach an existing project folder or initialize `.planningtree` metadata in an
  empty supported folder.
- Create only `meta.json` and `tree.json`.
- `.planningtree/workflow_core_v2/artifact_jobs.json` is created lazily when
  artifact jobs need project-level state.
- Create the root tree entry inline with:
  `title = name`, `description = root_goal`, `status = draft`, `node_kind = "root"`, `depth = 0`, `display_order = 0`, `hierarchical_number = "1"`.
- Set `active_node_id` to the root node id.
- New projects persist `schema_version = 6`.

## Listing Rules

- `GET /v4/projects` reads only `meta.json`.
- The frontend uses the list to populate the project selector.
- If the persisted active project id is missing or stale, the frontend should auto-load the newest listed project instead of leaving the graph empty.

## Compatibility Rules

- There is no migration path for unsupported old project storage.
- Older project layouts must return `409 unsupported_project_layout`.

