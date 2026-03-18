# Graph Workspace

## Legacy UI Port Scope

Use these legacy files as the design source:

- `PlanningTreeCodex/frontend/src/app/App.tsx`
- `PlanningTreeCodex/frontend/src/features/graph/WorkflowGraph.tsx`
- `PlanningTreeCodex/frontend/src/features/breadcrumb/BreadcrumbView.tsx`
- `PlanningTreeCodex/frontend/src/styles.css`

## Visual Requirements

- Port the top bar branding, theme switcher, and full-height workspace shell at high fidelity.
- Keep the Warm Earth theme as default and preserve the four alternate legacy themes.
- Port the graph background, node card proportions, border/shadow treatment, floating action affordance, detail panel, and fullscreen control at high fidelity.
- Rebuild the visuals with `tokens.css`, `globals.css`, and feature-scoped CSS Modules.

## Behavior Requirements

- Route `/` renders the graph workspace.
- Route `/projects/:projectId/nodes/:nodeId/chat` renders the breadcrumb execution workspace.
- The project root node must always be present in the ReactFlow node set when the snapshot is
  valid.
- The graph node action menu exposes:
  enabled `Create Child`
  enabled `Open Breadcrumb`
  enabled split actions `Workflow`, `Simplify Workflow`, `Phase Breakdown`, and `Agent Breakdown`
    when the node can split
  split actions become unavailable while another split is already in progress
  enabled `Finish Task` only for leaf nodes in `ready` or `in_progress`
- Locked nodes may still split; done nodes may not.
- No separate graph-side split panel exists. The `GraphNode` menu is the sole split entrypoint.
- The right-side floating detail panel is the main editing surface in Phase 3.
- Inline edits persist on blur and when selection changes.
- `Open Breadcrumb` performs unseeded navigation into the breadcrumb workspace.
- `Finish Task` flushes pending edits, navigates into the breadcrumb workspace, and seeds the composer via transient router state.
- `Mark Done` lives in the breadcrumb workspace and completes the node via the existing `/complete` endpoint.
