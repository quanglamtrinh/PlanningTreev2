# Agent Rules - PlanningTree

Rules for contributors working on the current repo state.

## Current Boundary

- `/` is the graph workspace.
- `/projects/:projectId/nodes/:nodeId/chat` is the breadcrumb chat surface (active development).
- Supported public backend surfaces are bootstrap/settings/projects, active-node selection, node create/update, and split launch/status.

## Before Writing Code

1. Read the current feature doc under `docs/features/` if one exists.
2. Prefer updating or deleting outdated docs instead of layering more historical caveats onto them.
3. Treat graph as the preserved user path. Breadcrumb chat is under active development.

## Naming Rules

| Legacy Term | Current Meaning |
|---|---|
| `prompt` | `description` |
| `short_title` | `title` |
| `finish_node` | `Finish Task` navigation action |
| `close_node` | retired public flow; do not re-add implicitly |
| `planned` | `ready` |
| `running` | `in_progress` |
| `closed` | `done` |

## Backend Rules

- Routes stay thin: validate input, call one service, return the result.
- Business rules live in services, not in routes or storage.
- Storage writes stay atomic through the shared helpers.
- Preserve the current route ownership:
  - project routes own bootstrap, settings, projects, snapshot, reset, and active-node selection
  - node routes own create-child, update-node, and split launch
  - split status is project-scoped
- Do not add new public route families without an approved spec.

## Frontend Rules

- Components do not call `fetch()` directly.
- Zustand stores own API coordination and local state transitions.
- `Open Breadcrumb` and `Finish Task` may navigate to `/chat`, but they must not pass `activeTab`, `RequestedTabId`, `composerSeed`, or similar transient contracts.
- Graph detail shells may use lightweight placeholders during rework.

## Common Mistakes To Avoid

1. Wiring product logic straight into routes because a flow currently looks small.
2. Adding new router-state contracts between graph and breadcrumb beyond what the chat spec defines.

## Adding A New Feature

1. Write or update the relevant `docs/features/<feature>.md`.
2. Define route and storage changes only for live product surfaces.
3. Implement service logic.
4. Implement route wiring.
5. Implement store wiring.
6. Implement UI.
7. Add focused frontend and backend tests.
