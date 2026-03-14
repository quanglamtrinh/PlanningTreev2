# Migration Plan - PlanningTree Rebuild

Version: 0.2.0-phase3
Last updated: 2026-03-08

## Strategy

This rebuild remains a clean break. `PlanningTreeCodex` is a read-only reference for product behavior, UI treatment, and selected implementation patterns, but not for state shape or architecture.

Each feature is implemented in this order:

1. Lock the feature spec in `docs/features/`
2. Implement storage -> service -> route -> frontend store -> frontend UI
3. Add unit and integration coverage

## Phase Map

| Build Phase | Features |
|---|---|
| Phase 2: Scaffold | Project foundation only |
| Phase 3: Core Graph + Project State | Bootstrap, workspace setup, projects, nodes, active node persistence, completion, legacy-style graph UI, breadcrumb placeholder |
| Phase 4: Breadcrumb Execution | Codex client, chat storage/service, SSE, Finish Task flow, Mark Done UI |
| Phase 5: AI Planning | OpenAI split client, context builder, split prompts, walking skeleton, slice, split UI |
| Phase 6: Distribution + Auth | Cloud auth, launcher polish, PyInstaller, npm packaging |

## Phase 3 Highlights

- Deliver a usable Graph Workspace from a clean install.
- Preserve the canonical simplified snapshot model with `tree_state.node_registry`.
- Port the legacy `PlanningTreeCodex` UI at high fidelity while keeping the new `PlanningTreeMain` store/router architecture.
- Do not port gate, rollback, version, preview, reconfirmation, audit, or SSE UI.

## Definition Of Done

A feature is complete when:

1. Its spec is committed under `docs/features/`
2. Backend and frontend behavior match the documented contract
3. Required unit and integration tests pass
4. No legacy gate-era concepts leak into the implementation
