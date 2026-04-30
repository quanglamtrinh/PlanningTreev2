# Bootstrap Settings

## Behavior

- `GET /v4/bootstrap/status` returns server readiness plus Codex path and feature status.
- Project folders are attached directly with `POST /v4/projects/attach`.
- The previous settings workspace route family is no longer part of the active public API.

## Validation

- The path must exist.
- The path must resolve to a directory.
- The directory must be writable.
- Invalid selections return `invalid_workspace_root`.

## Frontend

- On first load, the app checks bootstrap status.
- The app renders the graph shell and uses the project attach flow to add folders.

