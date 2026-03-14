# Project CRUD

## Routes

- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{project_id}/snapshot`

## Creation Rules

- Request body: `{ name, root_goal }`
- Create `<base_workspace_root>/<slugified-name>` for the project workspace.
- Resolve slug collisions with numeric suffixes: `-2`, `-3`, and so on.
- Create `meta.json`, `tree.json`, empty `chat_state.json`, empty `thread_state.json`, and a root node directory under `nodes/`.
- Create the root task document with:
  `title = name`, `purpose = root_goal`, `responsibility = ""`.
- Create the root tree entry with:
  `status = draft`, `phase = planning`, `depth = 0`, `display_order = 0`, `hierarchical_number = "1"`, `planning_mode = null`, `node_kind = "root"`, `chat_session_id = null`, `planning_thread_id = null`, `execution_thread_id = null`.
- Set `active_node_id` to the root node id.

## Listing Rules

- `GET /v1/projects` reads only `meta.json`.
- The frontend uses the list to populate the control rack project selector.
- If the persisted active project id is missing or stale, the frontend should auto-load the newest
  listed project instead of leaving Graph Workspace empty.
