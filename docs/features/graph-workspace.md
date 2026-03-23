# Graph Workspace

## Scope

The graph is the primary product surface in the current build.

- Route `/` renders the graph workspace.
- Route `/projects/:projectId/nodes/:nodeId/chat` renders the breadcrumb chat view.

## Behavior Requirements

- The root node must always be present when a valid snapshot is loaded.
- The graph node action menu exposes:
  - `Create Child`
  - `Workflow`
  - `Simplify Workflow`
  - `Phase Breakdown`
  - `Agent Breakdown`
  - `Open Breadcrumb`
  - `Finish Task` for eligible leaf nodes with confirmed spec
- Split actions start an async job and keep the target node in a busy state while polling project split status.
- Split actions are only eligible after the latest confirmed frame leaves no clarify questions, i.e. the node has advanced to the Spec workflow step.
- Split completion refreshes the snapshot; split failure surfaces an error banner.
- `Open Breadcrumb` and `Finish Task` both navigate to `/chat` without transient route-state contracts.
- The right-side detail shell remains present as a lightweight node-info panel.
- Inline graph edits still persist through the existing node update path.

## Explicit Non-Goals

- Adding new seeded route-state contracts between graph and breadcrumb
- Reintroducing split transcript or planning-history UI
