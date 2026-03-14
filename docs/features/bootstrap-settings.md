# Bootstrap Settings

## Behavior

- `GET /v1/bootstrap/status` returns `{ ready, workspace_configured }`.
- `ready` is equivalent to `workspace_configured` in Phase 3 because auth remains stubbed.
- `GET /v1/settings/workspace` returns `{ base_workspace_root }`.
- `PATCH /v1/settings/workspace` persists the selected base workspace root in `config/app.json`.

## Validation

- The path must exist.
- The path must resolve to a directory.
- The directory must be writable.
- Invalid selections return `invalid_workspace_root`.

## Frontend

- On first load, the app checks bootstrap status.
- If the workspace is missing, render `WorkspaceSetup`.
- If the workspace exists, render the graph shell.
